"""Tests for twag.db.time_utils — time range parsing and market cutoff."""

from datetime import datetime, timezone

from twag.db.time_utils import get_market_day_cutoff, parse_time_range


def test_parse_time_range_relative_hours():
    since, until = parse_time_range("24h")
    assert since is not None
    assert until is None
    assert since.tzinfo == timezone.utc
    # Should be roughly 24 hours ago
    delta = datetime.now(timezone.utc) - since
    assert 23.9 < delta.total_seconds() / 3600 < 24.1


def test_parse_time_range_relative_days():
    since, until = parse_time_range("7d")
    assert since is not None
    assert until is None
    delta = datetime.now(timezone.utc) - since
    assert 6.9 < delta.total_seconds() / 86400 < 7.1


def test_parse_time_range_relative_weeks():
    since, until = parse_time_range("1w")
    assert since is not None
    delta = datetime.now(timezone.utc) - since
    assert 6.9 < delta.total_seconds() / 86400 < 7.1


def test_parse_time_range_relative_months():
    since, until = parse_time_range("2m")
    assert since is not None
    delta = datetime.now(timezone.utc) - since
    assert 59 < delta.total_seconds() / 86400 < 61


def test_parse_time_range_single_date():
    since, until = parse_time_range("2025-01-15")
    assert since == datetime(2025, 1, 15, tzinfo=timezone.utc)
    assert until == datetime(2025, 1, 16, tzinfo=timezone.utc)


def test_parse_time_range_date_range():
    since, until = parse_time_range("2025-01-15..2025-01-20")
    assert since == datetime(2025, 1, 15, tzinfo=timezone.utc)
    assert until == datetime(2025, 1, 21, tzinfo=timezone.utc)


def test_parse_time_range_today():
    since, until = parse_time_range("today")
    assert since is not None
    assert until is None
    # "today" returns the market day cutoff
    assert since.tzinfo == timezone.utc


def test_parse_time_range_invalid():
    since, until = parse_time_range("garbage")
    assert since is None
    assert until is None


def test_parse_time_range_strips_whitespace():
    since, until = parse_time_range("  7d  ")
    assert since is not None


def test_get_market_day_cutoff_returns_utc():
    cutoff = get_market_day_cutoff()
    assert cutoff.tzinfo == timezone.utc


def test_get_market_day_cutoff_is_in_the_past():
    cutoff = get_market_day_cutoff()
    assert cutoff < datetime.now(timezone.utc)
