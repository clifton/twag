"""Narrative CRUD operations."""

import json
import sqlite3
from datetime import datetime, timezone


def upsert_narrative(
    conn: sqlite3.Connection,
    name: str,
    sentiment: str | None = None,
    tickers: list[str] | None = None,
) -> int:
    """Insert or update a narrative, returning its ID."""
    cursor = conn.execute(
        """
        INSERT INTO narratives (name, sentiment, related_tickers, last_mentioned_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            mention_count = mention_count + 1,
            last_mentioned_at = ?,
            sentiment = COALESCE(excluded.sentiment, sentiment)
        RETURNING id
        """,
        (
            name,
            sentiment,
            json.dumps(tickers) if tickers else None,
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    row = cursor.fetchone()
    return row[0] if row else 0


def get_active_narratives(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Get currently active narratives."""
    cursor = conn.execute(
        """
        SELECT * FROM narratives
        WHERE active = 1
        ORDER BY last_mentioned_at DESC
        """
    )
    return cursor.fetchall()


def link_tweet_narrative(conn: sqlite3.Connection, tweet_id: str, narrative_id: int) -> None:
    """Link a tweet to a narrative."""
    try:
        conn.execute(
            "INSERT INTO tweet_narratives (tweet_id, narrative_id) VALUES (?, ?)",
            (tweet_id, narrative_id),
        )
    except sqlite3.IntegrityError:
        pass  # Already linked


def archive_stale_narratives(conn: sqlite3.Connection, days: int = 7) -> int:
    """Mark narratives as inactive if not mentioned recently."""
    cursor = conn.execute(
        """
        UPDATE narratives
        SET active = 0
        WHERE last_mentioned_at < datetime('now', ?)
        AND active = 1
        """,
        (f"-{days} days",),
    )
    return cursor.rowcount
