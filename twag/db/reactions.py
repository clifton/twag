"""Reaction CRUD operations for feedback loop."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Reaction:
    """A user reaction to a tweet."""

    id: int
    tweet_id: str
    reaction_type: str
    reason: str | None
    target: str | None
    created_at: datetime | None


def insert_reaction(
    conn: sqlite3.Connection,
    tweet_id: str,
    reaction_type: str,
    reason: str | None = None,
    target: str | None = None,
) -> int:
    """Insert a reaction and return its ID."""
    cursor = conn.execute(
        """
        INSERT INTO reactions (tweet_id, reaction_type, reason, target)
        VALUES (?, ?, ?, ?)
        """,
        (tweet_id, reaction_type, reason, target),
    )
    return cursor.lastrowid or 0


def get_reactions_for_tweet(conn: sqlite3.Connection, tweet_id: str) -> list[Reaction]:
    """Get all reactions for a specific tweet."""
    cursor = conn.execute(
        """
        SELECT id, tweet_id, reaction_type, reason, target, created_at
        FROM reactions
        WHERE tweet_id = ?
        ORDER BY created_at DESC
        """,
        (tweet_id,),
    )
    results = []
    for row in cursor.fetchall():
        created_at = None
        if row["created_at"]:
            try:
                created_at = datetime.fromisoformat(row["created_at"])
            except ValueError:
                pass
        results.append(
            Reaction(
                id=row["id"],
                tweet_id=row["tweet_id"],
                reaction_type=row["reaction_type"],
                reason=row["reason"],
                target=row["target"],
                created_at=created_at,
            )
        )
    return results


def get_reactions_summary(conn: sqlite3.Connection) -> dict[str, int]:
    """Get count of reactions by type."""
    cursor = conn.execute(
        """
        SELECT reaction_type, COUNT(*) as count
        FROM reactions
        GROUP BY reaction_type
        """
    )
    return {row["reaction_type"]: row["count"] for row in cursor.fetchall()}


def get_reactions_with_tweets(
    conn: sqlite3.Connection,
    reaction_type: str | None = None,
    limit: int = 50,
) -> list[tuple[Reaction, sqlite3.Row]]:
    """Get reactions with their associated tweets for prompt tuning."""
    conditions = []
    params: list[Any] = []

    if reaction_type:
        conditions.append("r.reaction_type = ?")
        params.append(reaction_type)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    cursor = conn.execute(
        f"""
        SELECT
            r.id as reaction_id, r.tweet_id, r.reaction_type, r.reason, r.target, r.created_at as reaction_created_at,
            t.*
        FROM reactions r
        JOIN tweets t ON r.tweet_id = t.id
        {where_clause}
        ORDER BY r.created_at DESC
        LIMIT ?
        """,
        params,
    )

    results = []
    for row in cursor.fetchall():
        reaction_created_at = None
        if row["reaction_created_at"]:
            try:
                reaction_created_at = datetime.fromisoformat(row["reaction_created_at"])
            except ValueError:
                pass

        reaction = Reaction(
            id=row["reaction_id"],
            tweet_id=row["tweet_id"],
            reaction_type=row["reaction_type"],
            reason=row["reason"],
            target=row["target"],
            created_at=reaction_created_at,
        )
        results.append((reaction, row))
    return results


def delete_reaction(conn: sqlite3.Connection, reaction_id: int) -> bool:
    """Delete a reaction by ID. Returns True if deleted."""
    cursor = conn.execute("DELETE FROM reactions WHERE id = ?", (reaction_id,))
    return cursor.rowcount > 0
