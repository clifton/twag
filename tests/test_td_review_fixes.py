"""Tests for TD review fixes: alert rate limiting, tier thresholds, row_value helper."""

import sqlite3
from unittest.mock import patch

from twag.db import get_connection, init_db
from twag.db.alerts import get_recent_alert_count, log_alert
from twag.processor.triage import _score_to_signal_tier
from twag.text_utils import row_value

# --- P0-2: Alert rate limiting ---


def test_alert_log_table_created(tmp_path):
    """alert_log table is created by init_db."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alert_log'")
        assert cursor.fetchone() is not None


def test_get_recent_alert_count_empty(tmp_path):
    """Returns 0 when no alerts have been sent."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with get_connection(db_path) as conn:
        assert get_recent_alert_count(conn, minutes=60) == 0


def test_log_alert_and_count(tmp_path):
    """Logging an alert increments the recent count."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with get_connection(db_path) as conn:
        log_alert(conn, tweet_id="tweet123", chat_id="chat456")
        log_alert(conn, tweet_id="tweet789", chat_id="chat456")
        conn.commit()
        assert get_recent_alert_count(conn, minutes=60) == 2


def test_notifier_rate_limit_blocks(tmp_path):
    """can_send_alert returns False when rate limit is exceeded."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    # Patch get_connection and load_config to use test DB
    def _mock_config():
        return {
            "notifications": {
                "telegram_enabled": True,
                "quiet_hours_start": 0,
                "quiet_hours_end": 0,
                "max_alerts_per_hour": 2,
            },
            "scoring": {"alert_threshold": 8},
        }

    with get_connection(db_path) as conn:
        for i in range(3):
            log_alert(conn, tweet_id=f"t{i}")
        conn.commit()

    with (
        patch("twag.notifier.load_config", _mock_config),
        patch("twag.notifier.get_connection", lambda: get_connection(db_path)),
    ):
        from twag.notifier import can_send_alert

        assert can_send_alert(score=9) is False  # Rate limit hit (3 > 2)


def test_notifier_rate_limit_allows(tmp_path):
    """can_send_alert returns True when under rate limit."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    def _mock_config():
        return {
            "notifications": {
                "telegram_enabled": True,
                "quiet_hours_start": 0,
                "quiet_hours_end": 0,
                "max_alerts_per_hour": 10,
            },
            "scoring": {"alert_threshold": 8},
        }

    with (
        patch("twag.notifier.load_config", _mock_config),
        patch("twag.notifier.get_connection", lambda: get_connection(db_path)),
    ):
        from twag.notifier import can_send_alert

        assert can_send_alert(score=9) is True


# --- P0-3: Signal tier thresholds ---


def test_score_to_signal_tier_default_thresholds():
    """With default high_signal_threshold=7, tiers match expected boundaries."""
    assert _score_to_signal_tier(8.0, 7.0) == "high_signal"
    assert _score_to_signal_tier(7.5, 7.0) == "market_relevant"  # 7.5 < 8 (threshold+1)
    assert _score_to_signal_tier(7.0, 7.0) == "market_relevant"
    assert _score_to_signal_tier(6.0, 7.0) == "market_relevant"
    assert _score_to_signal_tier(5.0, 7.0) == "news"
    assert _score_to_signal_tier(4.0, 7.0) == "news"
    assert _score_to_signal_tier(3.9, 7.0) == "noise"
    assert _score_to_signal_tier(0.0, 7.0) == "noise"


def test_score_to_signal_tier_custom_threshold():
    """Custom high_signal_threshold shifts all tier boundaries."""
    # If threshold is 5: high_signal >= 6, market_relevant >= 4, news >= 2
    assert _score_to_signal_tier(6.0, 5.0) == "high_signal"
    assert _score_to_signal_tier(5.0, 5.0) == "market_relevant"
    assert _score_to_signal_tier(4.0, 5.0) == "market_relevant"
    assert _score_to_signal_tier(3.0, 5.0) == "news"
    assert _score_to_signal_tier(2.0, 5.0) == "news"
    assert _score_to_signal_tier(1.9, 5.0) == "noise"


# --- P2-1: row_value helper ---


def test_row_value_with_dict():
    """row_value works with plain dicts."""
    d = {"key": "val", "num": 42}
    assert row_value(d, "key") == "val"
    assert row_value(d, "num") == 42
    assert row_value(d, "missing") is None
    assert row_value(d, "missing", "default") == "default"


def test_row_value_with_sqlite_row(tmp_path):
    """row_value works with sqlite3.Row objects."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE t (a TEXT, b INTEGER)")
    conn.execute("INSERT INTO t VALUES ('hello', 99)")
    row = conn.execute("SELECT * FROM t").fetchone()
    conn.close()

    assert row_value(row, "a") == "hello"
    assert row_value(row, "b") == 99
    assert row_value(row, "missing") is None
    assert row_value(row, "missing", "fallback") == "fallback"
