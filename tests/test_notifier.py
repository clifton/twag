"""Tests for twag.notifier."""

from datetime import datetime

from twag.notifier import can_send_alert, format_alert, is_quiet_hours


class TestFormatAlert:
    def test_content_truncation(self):
        long_content = "x" * 200
        result = format_alert(
            tweet_id="123",
            author_handle="trader",
            content=long_content,
            category="macro",
            summary="Big move",
        )
        assert "x" * 150 + "..." in result

    def test_short_content_no_truncation(self):
        result = format_alert(
            tweet_id="123",
            author_handle="trader",
            content="Short tweet",
            category="macro",
            summary="",
        )
        assert "Short tweet" in result
        assert "..." not in result.split('"Short tweet"')[1].split("\n")[0]

    def test_category_list(self):
        result = format_alert(
            tweet_id="123",
            author_handle="trader",
            content="test",
            category=["earnings", "noise", "macro"],
            summary="",
        )
        # "noise" should be filtered out
        assert "EARNINGS" in result
        assert "MACRO" in result
        assert "NOISE" not in result

    def test_category_string(self):
        result = format_alert(
            tweet_id="123",
            author_handle="trader",
            content="test",
            category="breaking_news",
            summary="",
        )
        assert "BREAKING NEWS" in result

    def test_tickers_displayed(self):
        result = format_alert(
            tweet_id="123",
            author_handle="trader",
            content="test",
            category="macro",
            summary="",
            tickers=["AAPL", "MSFT"],
        )
        assert "AAPL" in result
        assert "MSFT" in result

    def test_url_constructed(self):
        result = format_alert(
            tweet_id="99999",
            author_handle="analyst",
            content="test",
            category="macro",
            summary="",
        )
        assert "https://x.com/analyst/status/99999" in result


class TestIsQuietHours:
    def test_within_quiet_hours(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {
                "notifications": {"quiet_hours_start": 23, "quiet_hours_end": 8},
            },
        )
        # 2am is within 23-8 range
        fake_now = datetime(2025, 6, 15, 2, 0, 0)
        monkeypatch.setattr(
            "twag.notifier.datetime",
            type(
                "FakeDT",
                (),
                {
                    "now": staticmethod(lambda: fake_now),
                },
            ),
        )
        assert is_quiet_hours() is True

    def test_outside_quiet_hours(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {
                "notifications": {"quiet_hours_start": 23, "quiet_hours_end": 8},
            },
        )
        fake_now = datetime(2025, 6, 15, 14, 0, 0)
        monkeypatch.setattr(
            "twag.notifier.datetime",
            type(
                "FakeDT",
                (),
                {
                    "now": staticmethod(lambda: fake_now),
                },
            ),
        )
        assert is_quiet_hours() is False

    def test_at_start_boundary(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {
                "notifications": {"quiet_hours_start": 23, "quiet_hours_end": 8},
            },
        )
        fake_now = datetime(2025, 6, 15, 23, 0, 0)
        monkeypatch.setattr(
            "twag.notifier.datetime",
            type(
                "FakeDT",
                (),
                {
                    "now": staticmethod(lambda: fake_now),
                },
            ),
        )
        assert is_quiet_hours() is True


class TestCanSendAlert:
    def test_disabled_returns_false(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {
                "notifications": {"telegram_enabled": False},
            },
        )
        assert can_send_alert(score=9) is False

    def test_score_10_overrides_quiet_hours(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {
                "notifications": {"telegram_enabled": True},
            },
        )
        monkeypatch.setattr("twag.notifier.is_quiet_hours", lambda: True)
        assert can_send_alert(score=10) is True

    def test_quiet_hours_blocks(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {
                "notifications": {"telegram_enabled": True},
            },
        )
        monkeypatch.setattr("twag.notifier.is_quiet_hours", lambda: True)
        assert can_send_alert(score=8) is False

    def test_rate_limit_blocks(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {
                "notifications": {"telegram_enabled": True, "max_alerts_per_hour": 5},
            },
        )
        monkeypatch.setattr("twag.notifier.is_quiet_hours", lambda: False)
        monkeypatch.setattr("twag.notifier.get_recent_alert_count", lambda: 5)
        assert can_send_alert(score=8) is False

    def test_allowed_when_all_checks_pass(self, monkeypatch):
        monkeypatch.setattr(
            "twag.notifier.load_config",
            lambda: {
                "notifications": {"telegram_enabled": True, "max_alerts_per_hour": 10},
            },
        )
        monkeypatch.setattr("twag.notifier.is_quiet_hours", lambda: False)
        monkeypatch.setattr("twag.notifier.get_recent_alert_count", lambda: 0)
        assert can_send_alert(score=8) is True
