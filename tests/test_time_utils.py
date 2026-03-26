"""Tests for twag.db.time_utils — parse_time_range and market day cutoff."""

from datetime import datetime, timezone
from unittest.mock import patch

from twag.db.time_utils import get_market_day_cutoff, parse_time_range


class TestParseTimeRange:
    def test_relative_hours(self):
        since, until = parse_time_range("24h")
        assert until is None
        assert since is not None
        diff = datetime.now(timezone.utc) - since
        assert abs(diff.total_seconds() - 86400) < 5

    def test_relative_days(self):
        since, until = parse_time_range("7d")
        assert until is None
        assert since is not None
        diff = datetime.now(timezone.utc) - since
        assert abs(diff.total_seconds() - 7 * 86400) < 5

    def test_relative_weeks(self):
        since, until = parse_time_range("1w")
        assert until is None
        assert since is not None
        diff = datetime.now(timezone.utc) - since
        assert abs(diff.total_seconds() - 7 * 86400) < 5

    def test_relative_months(self):
        since, until = parse_time_range("2m")
        assert until is None
        assert since is not None
        diff = datetime.now(timezone.utc) - since
        assert abs(diff.total_seconds() - 60 * 86400) < 5

    def test_single_date(self):
        since, until = parse_time_range("2025-01-15")
        assert since == datetime(2025, 1, 15, tzinfo=timezone.utc)
        assert until == datetime(2025, 1, 16, tzinfo=timezone.utc)

    def test_date_range(self):
        since, until = parse_time_range("2025-01-15..2025-01-20")
        assert since == datetime(2025, 1, 15, tzinfo=timezone.utc)
        assert until == datetime(2025, 1, 21, tzinfo=timezone.utc)

    def test_today(self):
        since, until = parse_time_range("today")
        assert since is not None
        assert until is None
        # Should be a market-day cutoff — in the past
        assert since <= datetime.now(timezone.utc)

    def test_invalid_returns_none(self):
        since, until = parse_time_range("garbage")
        assert since is None
        assert until is None

    def test_strips_whitespace(self):
        since, until = parse_time_range("  7d  ")
        assert since is not None
        assert until is None

    def test_case_insensitive(self):
        since, _ = parse_time_range("7D")
        assert since is not None


class TestGetMarketDayCutoff:
    def _mock_now(self, year, month, day, hour, minute=0):
        return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)

    def test_weekday_after_market_close(self):
        # Wednesday 9pm UTC = ~5pm ET (EDT) -> same day 4pm ET = 8pm UTC
        mock_now = self._mock_now(2025, 7, 16, 21, 0)  # Wed in EDT
        with patch("twag.db.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            cutoff = get_market_day_cutoff()
        assert cutoff.tzinfo == timezone.utc
        # Should be on the 16th (same day) at 20:00 UTC (4pm EDT)
        assert cutoff == datetime(2025, 7, 16, 20, 0, tzinfo=timezone.utc)

    def test_weekday_before_market_close(self):
        # Wednesday 2pm UTC = ~10am ET (EDT) -> previous business day (Tue) 4pm ET
        mock_now = self._mock_now(2025, 7, 16, 14, 0)  # Wed in EDT
        with patch("twag.db.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            cutoff = get_market_day_cutoff()
        assert cutoff == datetime(2025, 7, 15, 20, 0, tzinfo=timezone.utc)

    def test_saturday(self):
        # Saturday -> Friday 4pm ET
        mock_now = self._mock_now(2025, 7, 19, 15, 0)  # Sat in EDT
        with patch("twag.db.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            cutoff = get_market_day_cutoff()
        assert cutoff == datetime(2025, 7, 18, 20, 0, tzinfo=timezone.utc)

    def test_sunday(self):
        # Sunday -> Friday 4pm ET
        mock_now = self._mock_now(2025, 7, 20, 15, 0)  # Sun in EDT
        with patch("twag.db.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            cutoff = get_market_day_cutoff()
        assert cutoff == datetime(2025, 7, 18, 20, 0, tzinfo=timezone.utc)

    def test_monday_before_close(self):
        # Monday before market close -> Friday 4pm ET
        mock_now = self._mock_now(2025, 7, 21, 14, 0)  # Mon in EDT
        with patch("twag.db.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            cutoff = get_market_day_cutoff()
        assert cutoff == datetime(2025, 7, 18, 20, 0, tzinfo=timezone.utc)
