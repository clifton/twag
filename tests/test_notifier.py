"""Tests for twag.notifier — quiet hours, rate limiting, alert formatting."""

from datetime import datetime
from unittest.mock import patch

from twag.notifier import can_send_alert, format_alert, is_quiet_hours


class TestIsQuietHours:
    def _patch_hour(self, hour):
        return patch("twag.notifier.datetime", wraps=datetime)

    def test_inside_overnight_quiet_hours_late(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {"notifications": {"quiet_hours_start": 23, "quiet_hours_end": 8}},
        )
        with patch("twag.notifier.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 1, 23, 30)
            assert is_quiet_hours() is True

    def test_inside_overnight_quiet_hours_early(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {"notifications": {"quiet_hours_start": 23, "quiet_hours_end": 8}},
        )
        with patch("twag.notifier.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 1, 5, 0)
            assert is_quiet_hours() is True

    def test_outside_overnight_quiet_hours(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {"notifications": {"quiet_hours_start": 23, "quiet_hours_end": 8}},
        )
        with patch("twag.notifier.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 1, 12, 0)
            assert is_quiet_hours() is False

    def test_boundary_at_end(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {"notifications": {"quiet_hours_start": 23, "quiet_hours_end": 8}},
        )
        with patch("twag.notifier.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 1, 8, 0)
            assert is_quiet_hours() is False

    def test_same_day_range(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {"notifications": {"quiet_hours_start": 9, "quiet_hours_end": 17}},
        )
        with patch("twag.notifier.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 1, 12, 0)
            assert is_quiet_hours() is True


class TestCanSendAlert:
    def test_disabled_returns_false(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {"notifications": {"telegram_enabled": False}},
        )
        assert can_send_alert(score=10) is False

    def test_score_10_bypasses_quiet_hours(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {"notifications": {"telegram_enabled": True}},
        )
        monkeypatch.setattr("twag.notifier.is_quiet_hours", lambda: True)
        assert can_send_alert(score=10) is True

    def test_quiet_hours_blocks_normal_score(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {"notifications": {"telegram_enabled": True}},
        )
        monkeypatch.setattr("twag.notifier.is_quiet_hours", lambda: True)
        assert can_send_alert(score=8) is False

    def test_rate_limit_blocks(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {"notifications": {"telegram_enabled": True, "max_alerts_per_hour": 5}},
        )
        monkeypatch.setattr("twag.notifier.is_quiet_hours", lambda: False)
        monkeypatch.setattr("twag.notifier.get_recent_alert_count", lambda: 5)
        assert can_send_alert(score=8) is False

    def test_allows_when_under_rate_limit(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {"notifications": {"telegram_enabled": True, "max_alerts_per_hour": 10}},
        )
        monkeypatch.setattr("twag.notifier.is_quiet_hours", lambda: False)
        monkeypatch.setattr("twag.notifier.get_recent_alert_count", lambda: 3)
        assert can_send_alert(score=8) is True


class TestFormatAlert:
    def test_basic_output(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.get_tweet_url",
            lambda tid, handle: f"https://x.com/{handle}/status/{tid}",
        )
        result = format_alert(
            tweet_id="123",
            author_handle="analyst",
            content="Short content",
            category="macro",
            summary="Big move in bonds",
            tickers=["TLT", "ZB"],
        )
        assert "HIGH SIGNAL" in result
        assert "MACRO" in result
        assert "@analyst" in result
        assert "Short content" in result
        assert "Big move in bonds" in result
        assert "TLT, ZB" in result
        assert "https://x.com/analyst/status/123" in result

    def test_truncates_long_content(self, monkeypatch):
        monkeypatch.setattr("twag.notifier.get_tweet_url", lambda tid, handle: "https://x.com/x/status/1")
        long_content = "A" * 200
        result = format_alert("1", "user", long_content, "macro", "sum")
        assert "..." in result
        # Preview should be 150 chars + "..."
        assert "A" * 150 + "..." in result

    def test_category_list_filters_noise(self, monkeypatch):
        monkeypatch.setattr("twag.notifier.get_tweet_url", lambda tid, handle: "https://x.com/x/status/1")
        result = format_alert("1", "user", "content", ["noise", "earnings"], "sum")
        assert "EARNINGS" in result
        assert "NOISE" not in result

    def test_category_list_all_noise_falls_back_to_market(self, monkeypatch):
        monkeypatch.setattr("twag.notifier.get_tweet_url", lambda tid, handle: "https://x.com/x/status/1")
        result = format_alert("1", "user", "content", ["noise"], "sum")
        assert "MARKET" in result

    def test_no_tickers_section_when_empty(self, monkeypatch):
        monkeypatch.setattr("twag.notifier.get_tweet_url", lambda tid, handle: "https://x.com/x/status/1")
        result = format_alert("1", "user", "content", "macro", "sum", tickers=None)
        assert "Tickers" not in result
