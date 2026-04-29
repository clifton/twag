"""Alert log operations for notification rate limiting."""

import logging
import sqlite3

from .connection import execute_with_retry

log = logging.getLogger(__name__)


def get_recent_alert_count(conn: sqlite3.Connection, minutes: int = 60) -> int:
    """Get count of alerts sent in the last N minutes."""
    cursor = conn.execute(
        """
        SELECT COUNT(*) as cnt FROM alert_log
        WHERE sent_at >= datetime('now', ?)
        """,
        (f"-{minutes} minutes",),
    )
    row = cursor.fetchone()
    return row["cnt"] if row else 0


def log_alert(
    conn: sqlite3.Connection,
    tweet_id: str | None = None,
    chat_id: str | None = None,
) -> None:
    """Record that an alert was sent, for rate limiting."""
    execute_with_retry(
        conn,
        "INSERT INTO alert_log (tweet_id, chat_id) VALUES (?, ?)",
        (tweet_id, chat_id),
    )
