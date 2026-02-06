"""Account CRUD operations."""

import sqlite3
from datetime import datetime, timezone
from typing import Any


def upsert_account(
    conn: sqlite3.Connection,
    handle: str,
    display_name: str | None = None,
    tier: int = 2,
    category: str | None = None,
) -> None:
    """Insert or update an account."""
    conn.execute(
        """
        INSERT INTO accounts (handle, display_name, tier, category)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(handle) DO UPDATE SET
            display_name = COALESCE(excluded.display_name, display_name),
            tier = CASE WHEN excluded.tier < tier THEN excluded.tier ELSE tier END,
            category = COALESCE(excluded.category, category)
        """,
        (handle.lstrip("@"), display_name, tier, category),
    )


def get_accounts(
    conn: sqlite3.Connection,
    tier: int | None = None,
    include_muted: bool = False,
    limit: int | None = None,
    order_by_last_fetched: bool = False,
) -> list[sqlite3.Row]:
    """Get accounts, optionally filtered by tier."""
    conditions = []
    params: list[Any] = []

    if tier is not None:
        conditions.append("tier = ?")
        params.append(tier)

    if not include_muted:
        conditions.append("muted = 0")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Order by least recently fetched first if requested
    if order_by_last_fetched:
        order_clause = "ORDER BY COALESCE(last_fetched_at, '1970-01-01') ASC"
    else:
        order_clause = "ORDER BY tier ASC, weight DESC"

    limit_clause = f"LIMIT {limit}" if limit else ""

    cursor = conn.execute(
        f"""
        SELECT * FROM accounts
        {where_clause}
        {order_clause}
        {limit_clause}
        """,
        params,
    )
    return cursor.fetchall()


def update_account_last_fetched(conn: sqlite3.Connection, handle: str) -> None:
    """Update the last_fetched_at timestamp for an account."""
    conn.execute(
        """
        UPDATE accounts SET last_fetched_at = ?
        WHERE handle = ?
        """,
        (datetime.now(timezone.utc).isoformat(), handle.lstrip("@")),
    )


def update_account_stats(
    conn: sqlite3.Connection,
    handle: str,
    score: float,
    is_high_signal: bool = False,
) -> None:
    """Update account statistics after processing a tweet."""
    handle = handle.lstrip("@")

    conn.execute(
        """
        UPDATE accounts SET
            tweets_seen = tweets_seen + 1,
            tweets_kept = tweets_kept + CASE WHEN ? >= 5 THEN 1 ELSE 0 END,
            avg_relevance_score = (
                COALESCE(avg_relevance_score, 0) * tweets_seen + ?
            ) / (tweets_seen + 1),
            last_high_signal_at = CASE WHEN ? THEN ? ELSE last_high_signal_at END
        WHERE handle = ?
        """,
        (
            score,
            score,
            is_high_signal,
            datetime.now(timezone.utc).isoformat() if is_high_signal else None,
            handle,
        ),
    )


def apply_account_decay(conn: sqlite3.Connection, decay_rate: float = 0.05) -> int:
    """Apply decay to account weights. Returns number of affected accounts."""
    cursor = conn.execute(
        """
        UPDATE accounts
        SET weight = MAX(10, weight * (1 - ?))
        WHERE last_high_signal_at IS NULL
           OR last_high_signal_at < datetime('now', '-7 days')
        """,
        (decay_rate,),
    )
    return cursor.rowcount


def boost_account(conn: sqlite3.Connection, handle: str, amount: float = 5.0) -> None:
    """Boost an account's weight."""
    conn.execute(
        """
        UPDATE accounts
        SET weight = MIN(100, weight + ?)
        WHERE handle = ?
        """,
        (amount, handle.lstrip("@")),
    )


def promote_account(conn: sqlite3.Connection, handle: str) -> None:
    """Promote an account to tier 1."""
    conn.execute(
        "UPDATE accounts SET tier = 1 WHERE handle = ?",
        (handle.lstrip("@"),),
    )


def mute_account(conn: sqlite3.Connection, handle: str) -> None:
    """Mute an account."""
    conn.execute(
        "UPDATE accounts SET muted = 1 WHERE handle = ?",
        (handle.lstrip("@"),),
    )


def demote_account(conn: sqlite3.Connection, handle: str, tier: int = 2) -> None:
    """Demote an account to a lower tier."""
    conn.execute(
        "UPDATE accounts SET tier = ? WHERE handle = ?",
        (tier, handle.lstrip("@")),
    )
