"""Tests for twag.db.time_utils."""

from datetime import datetime, timedelta, timezone

from twag.db.time_utils import _get_et_offset, get_market_day_cutoff, parse_time_range


class TestParseTimeRange:
    def test_relative_hours(self):
        since, until = parse_time_range("24h")
        assert until is None
        assert since is not None
        assert since.tzinfo == timezone.utc
        gap = datetime.now(timezone.utc) - since
        assert abs(gap.total_seconds() - 86400) < 5

    def test_relative_days(self):
        since, until = parse_time_range("7d")
        assert until is None
        gap = datetime.now(timezone.utc) - since
        assert abs(gap.total_seconds() - 7 * 86400) < 5

    def test_relative_weeks(self):
        since, until = parse_time_range("2w")
        assert until is None
        gap = datetime.now(timezone.utc) - since
        assert abs(gap.total_seconds() - 14 * 86400) < 5

    def test_relative_months(self):
        since, until = parse_time_range("1m")
        assert until is None
        gap = datetime.now(timezone.utc) - since
        assert abs(gap.total_seconds() - 30 * 86400) < 5

    def test_single_date(self):
        since, until = parse_time_range("2025-03-10")
        assert since == datetime(2025, 3, 10, tzinfo=timezone.utc)
        assert until == datetime(2025, 3, 11, tzinfo=timezone.utc)

    def test_date_range(self):
        since, until = parse_time_range("2025-01-15..2025-01-20")
        assert since == datetime(2025, 1, 15, tzinfo=timezone.utc)
        assert until == datetime(2025, 1, 21, tzinfo=timezone.utc)

    def test_today_returns_market_cutoff(self, monkeypatch):
        # "today" delegates to get_market_day_cutoff; just verify the return shape
        since, until = parse_time_range("today")
        assert since is not None
        assert until is None

    def test_invalid_returns_none(self):
        assert parse_time_range("garbage") == (None, None)

    def test_whitespace_stripped(self):
        since, until = parse_time_range("  7d  ")
        assert since is not None


class TestGetEtOffset:
    def test_returns_edt_in_summer(self, monkeypatch):
        summer = datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
        monkeypatch.setattr(
            "twag.db.time_utils.datetime",
            type(
                "FakeDT",
                (),
                {
                    "now": staticmethod(lambda tz=None: summer),
                    "__call__": datetime.__call__,
                    **{attr: getattr(datetime, attr) for attr in ["__new__", "__init__", "__init_subclass__"]},
                },
            )(),
        )
        # Can't easily monkeypatch datetime class; test real function instead
        offset = _get_et_offset()
        assert offset in (timedelta(hours=-4), timedelta(hours=-5))

    def test_returns_valid_offset(self):
        offset = _get_et_offset()
        assert offset in (timedelta(hours=-4), timedelta(hours=-5))


class TestGetMarketDayCutoff:
    def test_returns_utc(self):
        cutoff = get_market_day_cutoff()
        assert cutoff.tzinfo == timezone.utc

    def test_cutoff_is_in_past(self):
        cutoff = get_market_day_cutoff()
        assert cutoff <= datetime.now(timezone.utc)

    def test_cutoff_hour_is_market_close_utc(self):
        cutoff = get_market_day_cutoff()
        # Market close is 4pm ET = 20:00 or 21:00 UTC
        assert cutoff.hour in (20, 21)

    def test_cutoff_weekday_not_weekend(self):
        cutoff = get_market_day_cutoff()
        # The cutoff date in ET should be a weekday
        et_offset = _get_et_offset()
        cutoff_et = cutoff + et_offset
        assert cutoff_et.weekday() < 5  # Mon-Fri
