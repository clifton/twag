"""Tests for twag.db.time_utils — time range parsing and market day cutoff."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from twag.db.time_utils import _get_et_offset, parse_time_range


class TestGetEtOffset:
    def test_summer_is_edt(self):
        """July should return EDT (-4h)."""
        summer = datetime(2025, 7, 15, 12, 0, tzinfo=timezone.utc)
        with patch("twag.db.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = summer
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = _get_et_offset()
        assert result == timedelta(hours=-4)

    def test_winter_is_est(self):
        """January should return EST (-5h)."""
        winter = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        with patch("twag.db.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = winter
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = _get_et_offset()
        assert result == timedelta(hours=-5)


class TestParseTimeRange:
    def test_relative_days(self):
        since, until = parse_time_range("7d")
        assert since is not None
        assert until is None
        # Should be roughly 7 days ago
        expected = datetime.now(timezone.utc) - timedelta(days=7)
        assert abs((since - expected).total_seconds()) < 2

    def test_relative_hours(self):
        since, until = parse_time_range("24h")
        assert since is not None
        expected = datetime.now(timezone.utc) - timedelta(hours=24)
        assert abs((since - expected).total_seconds()) < 2

    def test_relative_weeks(self):
        since, until = parse_time_range("1w")
        assert since is not None
        expected = datetime.now(timezone.utc) - timedelta(weeks=1)
        assert abs((since - expected).total_seconds()) < 2

    def test_relative_months(self):
        since, until = parse_time_range("2m")
        assert since is not None
        expected = datetime.now(timezone.utc) - timedelta(days=60)
        assert abs((since - expected).total_seconds()) < 2

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

    def test_invalid_input(self):
        since, until = parse_time_range("not-a-date")
        assert since is None
        assert until is None

    def test_whitespace_stripped(self):
        since, until = parse_time_range("  7d  ")
        assert since is not None

    def test_case_insensitive(self):
        since, until = parse_time_range("TODAY")
        assert since is not None
