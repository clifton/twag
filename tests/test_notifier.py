"""Tests for twag.notifier — alert formatting and send-gating logic."""

from unittest.mock import patch

from twag.notifier import can_send_alert, format_alert


class TestFormatAlert:
    def test_list_category_filters_noise(self):
        result = format_alert(
            tweet_id="123",
            author_handle="testuser",
            content="short content",
            category=["macro", "noise", "earnings"],
            summary="Big earnings beat",
        )
        assert "MACRO" in result
        assert "EARNINGS" in result
        assert "NOISE" not in result

    def test_string_category(self):
        result = format_alert(
            tweet_id="123",
            author_handle="testuser",
            content="content",
            category="breaking_news",
            summary="summary",
        )
        assert "BREAKING NEWS" in result

    def test_empty_category_list_defaults_to_market(self):
        result = format_alert(
            tweet_id="123",
            author_handle="testuser",
            content="content",
            category=["noise"],
            summary="summary",
        )
        assert "MARKET" in result

    def test_tickers_displayed(self):
        result = format_alert(
            tweet_id="123",
            author_handle="testuser",
            content="content",
            category="macro",
            summary="summary",
            tickers=["AAPL", "TSLA"],
        )
        assert "AAPL" in result
        assert "TSLA" in result

    def test_content_truncation(self):
        long_content = "x" * 200
        result = format_alert(
            tweet_id="123",
            author_handle="testuser",
            content=long_content,
            category="macro",
            summary="summary",
        )
        assert "..." in result
        # Truncated to 150 chars + "..."
        assert "x" * 151 not in result

    def test_short_content_not_truncated(self):
        result = format_alert(
            tweet_id="123",
            author_handle="testuser",
            content="short",
            category="macro",
            summary="summary",
        )
        assert "..." not in result.split("@testuser")[1].split("\n")[0]

    def test_empty_summary_omitted(self):
        result = format_alert(
            tweet_id="123",
            author_handle="testuser",
            content="content",
            category="macro",
            summary="",
        )
        # The summary emoji line should not appear
        lines = result.split("\n")
        assert not any(line.startswith("📊") for line in lines)

    def test_no_tickers_omitted(self):
        result = format_alert(
            tweet_id="123",
            author_handle="testuser",
            content="content",
            category="macro",
            summary="summary",
        )
        lines = result.split("\n")
        assert not any("Tickers" in line for line in lines)

    def test_tweet_url_included(self):
        result = format_alert(
            tweet_id="456",
            author_handle="trader",
            content="content",
            category="macro",
            summary="summary",
        )
        assert "x.com/trader/status/456" in result


class TestCanSendAlert:
    def _mock_config(self, overrides=None):
        base = {
            "notifications": {
                "telegram_enabled": True,
                "quiet_hours_start": 23,
                "quiet_hours_end": 8,
                "max_alerts_per_hour": 10,
            },
            "scoring": {"alert_threshold": 7},
        }
        if overrides:
            base["notifications"].update(overrides)
        return base

    def test_disabled_returns_false(self):
        config = self._mock_config({"telegram_enabled": False})
        with patch("twag.notifier.load_config", return_value=config):
            assert can_send_alert(score=9) is False

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

    def test_normal_conditions_allow(self):
        config = self._mock_config({"telegram_enabled": True})
        with (
            patch("twag.notifier.load_config", return_value=config),
            patch("twag.notifier.is_quiet_hours", return_value=False),
            patch("twag.notifier.get_recent_alert_count", return_value=0),
        ):
            assert can_send_alert(score=5) is True
