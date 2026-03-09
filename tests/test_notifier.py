"""Tests for twag.notifier."""

from datetime import datetime
from unittest.mock import patch

from twag.notifier import can_send_alert, format_alert, is_quiet_hours


class TestIsQuietHours:
    def _patch_now(self, hour):
        """Patch datetime.now to return a specific hour."""
        return patch(
            "twag.notifier.datetime",
            wraps=datetime,
            **{
                "now.return_value": datetime(2025, 6, 10, hour, 30, 0),
            },
        )

    @patch("twag.notifier.load_config")
    def test_overnight_wrap_late_night(self, mock_config):
        mock_config.return_value = {"notifications": {"quiet_hours_start": 23, "quiet_hours_end": 8}}
        with self._patch_now(23):
            assert is_quiet_hours() is True

    @patch("twag.notifier.load_config")
    def test_overnight_wrap_early_morning(self, mock_config):
        mock_config.return_value = {"notifications": {"quiet_hours_start": 23, "quiet_hours_end": 8}}
        with self._patch_now(3):
            assert is_quiet_hours() is True

    @patch("twag.notifier.load_config")
    def test_daytime_not_quiet(self, mock_config):
        mock_config.return_value = {"notifications": {"quiet_hours_start": 23, "quiet_hours_end": 8}}
        with self._patch_now(14):
            assert is_quiet_hours() is False

    @patch("twag.notifier.load_config")
    def test_edge_hour_start(self, mock_config):
        mock_config.return_value = {"notifications": {"quiet_hours_start": 23, "quiet_hours_end": 8}}
        with self._patch_now(8):
            # hour 8 is NOT quiet (< end means strictly less than)
            assert is_quiet_hours() is False


class TestCanSendAlert:
    @patch("twag.notifier.load_config")
    def test_disabled(self, mock_config):
        mock_config.return_value = {"notifications": {"telegram_enabled": False}}
        assert can_send_alert(score=9) is False

    @patch("twag.notifier.is_quiet_hours", return_value=True)
    @patch("twag.notifier.load_config")
    def test_score_10_overrides_quiet(self, mock_config, mock_quiet):
        mock_config.return_value = {"notifications": {"telegram_enabled": True}}
        assert can_send_alert(score=10) is True

    @patch("twag.notifier.is_quiet_hours", return_value=True)
    @patch("twag.notifier.load_config")
    def test_quiet_hours_block(self, mock_config, mock_quiet):
        mock_config.return_value = {"notifications": {"telegram_enabled": True}}
        assert can_send_alert(score=7) is False

    @patch("twag.notifier.get_recent_alert_count", return_value=10)
    @patch("twag.notifier.is_quiet_hours", return_value=False)
    @patch("twag.notifier.load_config")
    def test_rate_limit(self, mock_config, mock_quiet, mock_count):
        mock_config.return_value = {"notifications": {"telegram_enabled": True, "max_alerts_per_hour": 10}}
        assert can_send_alert(score=7) is False


class TestFormatAlert:
    @patch("twag.notifier.get_tweet_url", return_value="https://x.com/user/status/123")
    def test_string_category(self, mock_url):
        result = format_alert("123", "user", "some content", "macro_event", "summary here")
        assert "MACRO EVENT" in result
        assert "@user" in result

    @patch("twag.notifier.get_tweet_url", return_value="https://x.com/user/status/123")
    def test_list_category(self, mock_url):
        result = format_alert("123", "user", "content", ["earnings", "noise"], "summary")
        assert "EARNINGS" in result
        assert "NOISE" not in result

    @patch("twag.notifier.get_tweet_url", return_value="https://x.com/user/status/123")
    def test_ticker_display(self, mock_url):
        result = format_alert("123", "user", "content", "macro", "summary", tickers=["AAPL", "TSLA"])
        assert "AAPL, TSLA" in result

    @patch("twag.notifier.get_tweet_url", return_value="https://x.com/user/status/123")
    def test_content_truncation(self, mock_url):
        long_content = "x" * 200
        result = format_alert("123", "user", long_content, "macro", "summary")
        assert "..." in result
        # Preview should be 150 chars + "..."
        assert "x" * 150 + "..." in result
