"""Tests for twag.notifier — alert formatting and send-gating logic."""

from unittest.mock import patch

from twag.notifier import can_send_alert, format_alert


class TestFormatAlert:
    def test_list_category_filters_noise(self):
        result = format_alert(
            tweet_id="123",
            author_handle="trader",
            content="Short content",
            category=["macro", "noise", "earnings"],
            summary="Key insight",
        )
        assert "MACRO, EARNINGS" in result
        assert "NOISE" not in result

    def test_list_category_all_noise_falls_back(self):
        result = format_alert(
            tweet_id="123",
            author_handle="trader",
            content="Short content",
            category=["noise"],
            summary="",
        )
        assert "MARKET" in result

    def test_string_category(self):
        result = format_alert(
            tweet_id="123",
            author_handle="trader",
            content="Short content",
            category="breaking_news",
            summary="",
        )
        assert "BREAKING NEWS" in result

    def test_empty_category(self):
        result = format_alert(
            tweet_id="123",
            author_handle="trader",
            content="Short content",
            category="",
            summary="",
        )
        assert "MARKET" in result

    def test_ticker_display(self):
        result = format_alert(
            tweet_id="123",
            author_handle="trader",
            content="Short",
            category="macro",
            summary="",
            tickers=["AAPL", "MSFT"],
        )
        assert "AAPL, MSFT" in result

    def test_content_truncation(self):
        long_content = "x" * 200
        result = format_alert(
            tweet_id="123",
            author_handle="trader",
            content=long_content,
            category="macro",
            summary="",
        )
        assert "..." in result
        # The preview should be 150 chars + "..."
        assert ("x" * 150 + "...") in result

    def test_short_content_no_truncation(self):
        result = format_alert(
            tweet_id="123",
            author_handle="trader",
            content="short",
            category="macro",
            summary="",
        )
        assert "..." not in result

    def test_tweet_url_included(self):
        result = format_alert(
            tweet_id="456",
            author_handle="someone",
            content="test",
            category="macro",
            summary="",
        )
        assert "https://x.com/someone/status/456" in result

    def test_summary_included(self):
        result = format_alert(
            tweet_id="123",
            author_handle="trader",
            content="test",
            category="macro",
            summary="Important development",
        )
        assert "Important development" in result


class TestCanSendAlert:
    def _mock_config(self, overrides=None):
        base = {
            "notifications": {
                "telegram_enabled": True,
                "quiet_hours_start": 23,
                "quiet_hours_end": 8,
                "max_alerts_per_hour": 10,
            },
        }
        if overrides:
            base["notifications"].update(overrides)
        return base

    def test_disabled_returns_false(self):
        config = self._mock_config({"telegram_enabled": False})
        with patch("twag.notifier.load_config", return_value=config):
            assert can_send_alert(score=5) is False

    def test_score_10_overrides_quiet_hours(self):
        config = self._mock_config({"telegram_enabled": True})
        with (
            patch("twag.notifier.load_config", return_value=config),
            patch("twag.notifier.is_quiet_hours", return_value=True),
        ):
            assert can_send_alert(score=10) is True

    def test_quiet_hours_blocks(self):
        config = self._mock_config({"telegram_enabled": True})
        with (
            patch("twag.notifier.load_config", return_value=config),
            patch("twag.notifier.is_quiet_hours", return_value=True),
        ):
            assert can_send_alert(score=5) is False

    def test_rate_limit_blocks(self):
        config = self._mock_config({"telegram_enabled": True, "max_alerts_per_hour": 5})
        with (
            patch("twag.notifier.load_config", return_value=config),
            patch("twag.notifier.is_quiet_hours", return_value=False),
            patch("twag.notifier.get_recent_alert_count", return_value=5),
        ):
            assert can_send_alert(score=5) is False

    def test_allowed_when_all_checks_pass(self):
        config = self._mock_config({"telegram_enabled": True})
        with (
            patch("twag.notifier.load_config", return_value=config),
            patch("twag.notifier.is_quiet_hours", return_value=False),
            patch("twag.notifier.get_recent_alert_count", return_value=0),
        ):
            assert can_send_alert(score=7) is True
