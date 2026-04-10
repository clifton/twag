"""Versioned schema migration framework for twag.

Each migration is a numbered step that transforms the database schema.
Migrations are tracked via PRAGMA user_version and recorded in a
schema_migrations audit table for traceability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Migration:
    """A single schema migration step."""

    version: int
    name: str
    description: str
    apply: Callable[[sqlite3.Connection], None]


# ---------------------------------------------------------------------------
# Migration functions
# ---------------------------------------------------------------------------


def _v1_baseline(conn: sqlite3.Connection) -> None:
    """Baseline schema — tables already created by SCHEMA constant."""


def _v2_bookmarks(conn: sqlite3.Connection) -> None:
    """Add bookmark columns to tweets."""
    cols = _get_columns(conn, "tweets")
    if "bookmarked" not in cols:
        conn.execute("ALTER TABLE tweets ADD COLUMN bookmarked INTEGER DEFAULT 0")
    if "bookmarked_at" not in cols:
        conn.execute("ALTER TABLE tweets ADD COLUMN bookmarked_at TIMESTAMP")


def _v3_content_summary(conn: sqlite3.Connection) -> None:
    """Add content_summary and media_items columns."""
    cols = _get_columns(conn, "tweets")
    if "content_summary" not in cols:
        conn.execute("ALTER TABLE tweets ADD COLUMN content_summary TEXT")
    if "media_items" not in cols:
        conn.execute("ALTER TABLE tweets ADD COLUMN media_items TEXT")
    if "analysis_json" not in cols:
        conn.execute("ALTER TABLE tweets ADD COLUMN analysis_json TEXT")


def _v4_retweets(conn: sqlite3.Connection) -> None:
    """Add retweet tracking columns."""
    cols = _get_columns(conn, "tweets")
    for col, typedef in [
        ("is_retweet", "INTEGER DEFAULT 0"),
        ("retweeted_by_handle", "TEXT"),
        ("retweeted_by_name", "TEXT"),
        ("original_tweet_id", "TEXT"),
        ("original_author_handle", "TEXT"),
        ("original_author_name", "TEXT"),
        ("original_content", "TEXT"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE tweets ADD COLUMN {col} {typedef}")


def _v5_articles(conn: sqlite3.Connection) -> None:
    """Add X Article processing columns."""
    cols = _get_columns(conn, "tweets")
    for col, typedef in [
        ("is_x_article", "INTEGER DEFAULT 0"),
        ("article_title", "TEXT"),
        ("article_preview", "TEXT"),
        ("article_text", "TEXT"),
        ("article_summary_short", "TEXT"),
        ("article_primary_points_json", "TEXT"),
        ("article_action_items_json", "TEXT"),
        ("article_top_visual_json", "TEXT"),
        ("article_processed_at", "TIMESTAMP"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE tweets ADD COLUMN {col} {typedef}")


def _v6_links(conn: sqlite3.Connection) -> None:
    """Add link expansion and reply columns."""
    cols = _get_columns(conn, "tweets")
    for col, typedef in [
        ("links_json", "TEXT"),
        ("in_reply_to_tweet_id", "TEXT"),
        ("conversation_id", "TEXT"),
        ("links_expanded_at", "TIMESTAMP"),
        ("quote_reprocessed_at", "TIMESTAMP"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE tweets ADD COLUMN {col} {typedef}")


def _v7_replies_indexes(conn: sqlite3.Connection) -> None:
    """Create performance indexes."""
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tweets_processed_score "
        "ON tweets(processed_at, relevance_score DESC, created_at DESC)",
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tweets_author ON tweets(author_handle)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tweets_signal_tier ON tweets(signal_tier)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tweets_bookmarked ON tweets(bookmarked) WHERE bookmarked = 1",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tweets_quote ON tweets(quote_tweet_id) WHERE quote_tweet_id IS NOT NULL",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tweets_reply "
        "ON tweets(in_reply_to_tweet_id) WHERE in_reply_to_tweet_id IS NOT NULL",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fetch_log_endpoint ON fetch_log(endpoint, executed_at DESC)",
    )


def _v8_alert_log(conn: sqlite3.Connection) -> None:
    """Create alert_log table for notification rate limiting."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tweet_id TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            chat_id TEXT,
            FOREIGN KEY (tweet_id) REFERENCES tweets(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_log_sent ON alert_log(sent_at DESC)")


def _v9_metrics(conn: sqlite3.Connection) -> None:
    """Create metrics table for instrumentation."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            value REAL NOT NULL,
            labels_json TEXT,
            recorded_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name, recorded_at DESC)")


def _v10_accounts_last_fetched(conn: sqlite3.Connection) -> None:
    """Add last_fetched_at column to accounts."""
    cols = _get_columns(conn, "accounts")
    if "last_fetched_at" not in cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN last_fetched_at TIMESTAMP")


# ---------------------------------------------------------------------------
# Migration registry — order matters, append new migrations at the end
# ---------------------------------------------------------------------------

MIGRATIONS: list[Migration] = [
    Migration(1, "baseline", "Initial schema creation", _v1_baseline),
    Migration(2, "bookmarks", "Add bookmark columns to tweets", _v2_bookmarks),
    Migration(3, "content_summary", "Add content_summary, media_items, analysis_json", _v3_content_summary),
    Migration(4, "retweets", "Add retweet tracking columns", _v4_retweets),
    Migration(5, "articles", "Add X Article processing columns", _v5_articles),
    Migration(6, "links", "Add link expansion and reply columns", _v6_links),
    Migration(7, "replies_indexes", "Create performance indexes", _v7_replies_indexes),
    Migration(8, "alert_log", "Create alert_log table", _v8_alert_log),
    Migration(9, "metrics", "Create metrics table", _v9_metrics),
    Migration(10, "accounts_last_fetched", "Add last_fetched_at to accounts", _v10_accounts_last_fetched),
]

LATEST_VERSION = MIGRATIONS[-1].version


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def get_current_version(conn: sqlite3.Connection) -> int:
    """Read the current schema version from PRAGMA user_version."""
    cursor = conn.execute("PRAGMA user_version")
    return cursor.fetchone()[0]


def get_pending_migrations(current_version: int) -> list[Migration]:
    """Return migrations that have not yet been applied."""
    return [m for m in MIGRATIONS if m.version > current_version]


def get_expected_tables() -> dict[str, set[str]]:
    """Return expected table→columns mapping from the full schema.

    This is a static snapshot of what the latest schema should contain.
    """
    return {
        "tweets": {
            "id",
            "author_handle",
            "author_name",
            "content",
            "created_at",
            "first_seen_at",
            "source",
            "processed_at",
            "relevance_score",
            "category",
            "summary",
            "content_summary",
            "signal_tier",
            "tickers",
            "analysis_json",
            "has_quote",
            "quote_tweet_id",
            "in_reply_to_tweet_id",
            "conversation_id",
            "has_media",
            "media_analysis",
            "media_items",
            "has_link",
            "links_json",
            "link_summary",
            "is_x_article",
            "article_title",
            "article_preview",
            "article_text",
            "article_summary_short",
            "article_primary_points_json",
            "article_action_items_json",
            "article_top_visual_json",
            "article_processed_at",
            "links_expanded_at",
            "quote_reprocessed_at",
            "is_retweet",
            "retweeted_by_handle",
            "retweeted_by_name",
            "original_tweet_id",
            "original_author_handle",
            "original_author_name",
            "original_content",
            "included_in_digest",
            "bookmarked",
            "bookmarked_at",
        },
        "accounts": {
            "handle",
            "display_name",
            "tier",
            "weight",
            "category",
            "tweets_seen",
            "tweets_kept",
            "avg_relevance_score",
            "last_high_signal_at",
            "last_fetched_at",
            "added_at",
            "auto_promoted",
            "muted",
        },
        "narratives": {
            "id",
            "name",
            "first_seen_at",
            "last_mentioned_at",
            "mention_count",
            "sentiment",
            "related_tickers",
            "active",
        },
        "tweet_narratives": {"tweet_id", "narrative_id"},
        "fetch_log": {
            "id",
            "endpoint",
            "executed_at",
            "tweets_fetched",
            "new_tweets",
            "query_params",
        },
        "reactions": {
            "id",
            "tweet_id",
            "reaction_type",
            "reason",
            "target",
            "created_at",
        },
        "prompts": {
            "id",
            "name",
            "template",
            "version",
            "updated_at",
            "updated_by",
        },
        "prompt_history": {
            "id",
            "prompt_name",
            "template",
            "version",
            "created_at",
        },
        "context_commands": {
            "id",
            "name",
            "command_template",
            "description",
            "enabled",
            "created_at",
        },
        "alert_log": {"id", "tweet_id", "sent_at", "chat_id"},
        "metrics": {"name", "type", "value", "labels_json", "recorded_at"},
    }


def record_migration(conn: sqlite3.Connection, migration: Migration) -> None:
    """Record a migration in the schema_migrations audit table."""
    conn.execute(
        "INSERT INTO schema_migrations (version, name, description) VALUES (?, ?, ?)",
        (migration.version, migration.name, migration.description),
    )


def apply_migration(conn: sqlite3.Connection, migration: Migration) -> None:
    """Apply a single migration and record it."""
    log.info("Applying migration v%d: %s", migration.version, migration.name)
    migration.apply(conn)
    record_migration(conn, migration)
    conn.execute(f"PRAGMA user_version = {migration.version}")


def run_pending_migrations(conn: sqlite3.Connection, *, dry_run: bool = False) -> list[Migration]:
    """Run all pending migrations. Returns list of applied migrations.

    If dry_run is True, no changes are made — only returns what would run.
    """
    ensure_schema_migrations_table(conn)
    current = get_current_version(conn)
    pending = get_pending_migrations(current)

    if dry_run:
        return pending

    for migration in pending:
        apply_migration(conn, migration)

    return pending


def ensure_schema_migrations_table(conn: sqlite3.Connection) -> None:
    """Create the schema_migrations audit table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def get_applied_migrations(conn: sqlite3.Connection) -> list[dict]:
    """Return all recorded migrations from the audit table."""
    ensure_schema_migrations_table(conn)
    cursor = conn.execute("SELECT version, name, description, applied_at FROM schema_migrations ORDER BY version")
    return [
        {"version": row[0], "name": row[1], "description": row[2], "applied_at": row[3]} for row in cursor.fetchall()
    ]
