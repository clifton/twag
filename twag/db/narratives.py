"""Narrative CRUD operations."""

import sqlite3


def get_active_narratives(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Get currently active narratives."""
    cursor = conn.execute(
        """
        SELECT * FROM narratives
        WHERE active = 1
        ORDER BY last_mentioned_at DESC
        """,
    )
    return cursor.fetchall()


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
