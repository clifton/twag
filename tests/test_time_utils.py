"""Tests for twag.db.time_utils."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from twag.db.time_utils import get_market_day_cutoff, parse_time_range


class TestParseTimeRange:
    def test_relative_duration_days(self):
        with patch("twag.db.time_utils.datetime") as mock_dt:
            now = datetime(2025, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = now
            mock_dt.strptime = datetime.strptime
            since, until = parse_time_range("7d")
            assert since == now - timedelta(days=7)
            assert until is None

    def test_relative_duration_hours(self):
        with patch("twag.db.time_utils.datetime") as mock_dt:
            now = datetime(2025, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = now
            mock_dt.strptime = datetime.strptime
            since, until = parse_time_range("24h")
            assert since == now - timedelta(hours=24)
            assert until is None

    def test_relative_duration_weeks(self):
        with patch("twag.db.time_utils.datetime") as mock_dt:
            now = datetime(2025, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = now
            mock_dt.strptime = datetime.strptime
            since, until = parse_time_range("1w")
            assert since == now - timedelta(weeks=1)
            assert until is None

    def test_relative_duration_months(self):
        with patch("twag.db.time_utils.datetime") as mock_dt:
            now = datetime(2025, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = now
            mock_dt.strptime = datetime.strptime
            since, until = parse_time_range("1m")
            assert since == now - timedelta(days=30)
            assert until is None

    def test_single_date(self):
        since, until = parse_time_range("2025-01-15")
        assert since == datetime(2025, 1, 15, tzinfo=timezone.utc)
        assert until == datetime(2025, 1, 16, tzinfo=timezone.utc)

    def test_date_range(self):
        since, until = parse_time_range("2025-01-15..2025-01-20")
        assert since == datetime(2025, 1, 15, tzinfo=timezone.utc)
        assert until == datetime(2025, 1, 21, tzinfo=timezone.utc)

    def test_today(self):
        with patch("twag.db.time_utils.get_market_day_cutoff") as mock_cutoff:
            cutoff = datetime(2025, 6, 9, 20, 0, 0, tzinfo=timezone.utc)
            mock_cutoff.return_value = cutoff
            since, until = parse_time_range("today")
            assert since == cutoff
            assert until is None

    def test_invalid_input(self):
        since, until = parse_time_range("garbage")
        assert since is None
        assert until is None

    def test_whitespace_stripped(self):
        since, until = parse_time_range("  2025-01-15  ")
        assert since == datetime(2025, 1, 15, tzinfo=timezone.utc)


class TestGetMarketDayCutoff:
    def _mock_now(self, dt_utc):
        """Patch datetime.now to return a specific UTC time."""
        return patch(
            "twag.db.time_utils.datetime",
            wraps=datetime,
            **{
                "now.return_value": dt_utc,
            },
        )

    def test_weekday_after_4pm_et(self):
        # Wednesday 2025-06-11 at 21:00 UTC = 5pm ET (EDT, -4)
        now = datetime(2025, 6, 11, 21, 0, 0, tzinfo=timezone.utc)
        with patch("twag.db.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            cutoff = get_market_day_cutoff()
            # Should be same day 4pm ET = 20:00 UTC (EDT)
            assert cutoff == datetime(2025, 6, 11, 20, 0, 0, tzinfo=timezone.utc)

    def test_weekday_before_4pm_et(self):
        # Wednesday 2025-06-11 at 15:00 UTC = 11am ET (EDT, -4)
        now = datetime(2025, 6, 11, 15, 0, 0, tzinfo=timezone.utc)
        with patch("twag.db.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            cutoff = get_market_day_cutoff()
            # Should be previous day (Tuesday) 4pm ET = 20:00 UTC
            assert cutoff == datetime(2025, 6, 10, 20, 0, 0, tzinfo=timezone.utc)

    def test_saturday(self):
        # Saturday 2025-06-14 at 15:00 UTC
        now = datetime(2025, 6, 14, 15, 0, 0, tzinfo=timezone.utc)
        with patch("twag.db.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            cutoff = get_market_day_cutoff()
            # Should be Friday 4pm ET = 20:00 UTC
            assert cutoff == datetime(2025, 6, 13, 20, 0, 0, tzinfo=timezone.utc)

    def test_sunday(self):
        # Sunday 2025-06-15 at 15:00 UTC
        now = datetime(2025, 6, 15, 15, 0, 0, tzinfo=timezone.utc)
        with patch("twag.db.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            cutoff = get_market_day_cutoff()
            # Should be Friday 4pm ET = 20:00 UTC
            assert cutoff == datetime(2025, 6, 13, 20, 0, 0, tzinfo=timezone.utc)

    def test_monday_before_4pm_et(self):
        # Monday 2025-06-16 at 14:00 UTC = 10am ET (EDT)
        now = datetime(2025, 6, 16, 14, 0, 0, tzinfo=timezone.utc)
        with patch("twag.db.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            cutoff = get_market_day_cutoff()
            # Should be previous Friday 4pm ET = 20:00 UTC
            assert cutoff == datetime(2025, 6, 13, 20, 0, 0, tzinfo=timezone.utc)
