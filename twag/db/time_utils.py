"""Time utility functions for database queries."""

import re
from datetime import datetime, timedelta, timezone


def _get_et_offset() -> timedelta:
    """Get current Eastern Time offset from UTC (handles DST approximately)."""
    now = datetime.now(timezone.utc)
    # DST roughly runs from second Sunday in March to first Sunday in November
    year = now.year
    # March: second Sunday
    march_start = datetime(year, 3, 8, tzinfo=timezone.utc)
    while march_start.weekday() != 6:  # Sunday
        march_start += timedelta(days=1)
    # November: first Sunday
    nov_start = datetime(year, 11, 1, tzinfo=timezone.utc)
    while nov_start.weekday() != 6:
        nov_start += timedelta(days=1)

    if march_start <= now < nov_start:
        return timedelta(hours=-4)  # EDT
    return timedelta(hours=-5)  # EST


def get_market_day_cutoff() -> datetime:
    """
    Get the previous market close (4pm ET) as a UTC datetime.

    - Weekday before 4pm ET -> previous business day's 4pm
    - Weekday after 4pm ET -> same day's 4pm
    - Saturday -> Friday 4pm
    - Sunday -> Friday 4pm
    """
    et_offset = _get_et_offset()
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc + et_offset

    # Market close is 4pm ET (16:00)
    market_close_hour = 16

    # Start with today's date in ET
    today_et = now_et.date()
    weekday = today_et.weekday()  # 0=Monday, 6=Sunday

    # Determine the cutoff date
    if weekday == 5:  # Saturday
        cutoff_date = today_et - timedelta(days=1)  # Friday
    elif weekday == 6:  # Sunday
        cutoff_date = today_et - timedelta(days=2)  # Friday
    elif now_et.hour < market_close_hour:
        # Before 4pm on a weekday - use previous business day
        if weekday == 0:  # Monday
            cutoff_date = today_et - timedelta(days=3)  # Friday
        else:
            cutoff_date = today_et - timedelta(days=1)
    else:
        # After 4pm on a weekday - use today
        cutoff_date = today_et

    # Build the cutoff datetime (4pm ET on cutoff_date)
    cutoff_et = datetime(cutoff_date.year, cutoff_date.month, cutoff_date.day, market_close_hour, 0, 0)

    # Convert back to UTC
    cutoff_utc = cutoff_et - et_offset
    return cutoff_utc.replace(tzinfo=timezone.utc)


def parse_time_range(spec: str) -> tuple[datetime | None, datetime | None]:
    """
    Parse a time range specification.

    Supported formats:
    - "today" -> since previous market close (4pm ET)
    - "7d", "24h", "1w" -> relative durations
    - "2025-01-15" -> specific date (full day)
    - "2025-01-15..2025-01-20" -> date range

    Returns (since, until) as UTC datetimes.
    """
    spec = spec.strip().lower()
    now = datetime.now(timezone.utc)

    if spec == "today":
        return (get_market_day_cutoff(), None)

    # Relative duration: 7d, 24h, 1w
    duration_match = re.match(r"^(\d+)([hdwm])$", spec)
    if duration_match:
        amount = int(duration_match.group(1))
        unit = duration_match.group(2)

        if unit == "h":
            delta = timedelta(hours=amount)
        elif unit == "d":
            delta = timedelta(days=amount)
        elif unit == "w":
            delta = timedelta(weeks=amount)
        elif unit == "m":
            delta = timedelta(days=amount * 30)  # Approximate
        else:
            delta = timedelta(days=amount)

        return (now - delta, None)

    # Date range: YYYY-MM-DD..YYYY-MM-DD
    if ".." in spec:
        parts = spec.split("..")
        if len(parts) == 2:
            try:
                since = datetime.strptime(parts[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                until = datetime.strptime(parts[1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                # End of day for until
                until = until + timedelta(days=1)
                return (since, until)
            except ValueError:
                pass

    # Single date: YYYY-MM-DD
    try:
        date = datetime.strptime(spec, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (date, date + timedelta(days=1))
    except ValueError:
        pass

    return (None, None)
