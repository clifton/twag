"""Versioned schema migration framework using PRAGMA user_version.

Each migration is a (version, description, callable) entry. Migrations run
in order when the database's user_version is below the target version.
SQLite lacks ALTER TABLE ... IF NOT EXISTS, so column additions use
try/except to stay idempotent.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable

log = logging.getLogger(__name__)

# Type alias for a migration entry
Migration = tuple[int, str, list[str]]

# ---------------------------------------------------------------------------
# Migration registry — append-only, never reorder or delete entries.
# Each entry: (version, description, sql_statements)
# SQL statements are executed in order. For ALTER TABLE, wrap with
# _safe_alter() at runtime since SQLite does not support IF NOT EXISTS.
# ---------------------------------------------------------------------------

_ALTER_COLUMNS_V1: list[tuple[str, str]] = [
    # tweets table columns
    ("tweets", "bookmarked INTEGER DEFAULT 0"),
    ("tweets", "bookmarked_at TIMESTAMP"),
    ("tweets", "content_summary TEXT"),
    ("tweets", "media_items TEXT"),
    ("tweets", "analysis_json TEXT"),
    ("tweets", "is_retweet INTEGER DEFAULT 0"),
    ("tweets", "retweeted_by_handle TEXT"),
    ("tweets", "retweeted_by_name TEXT"),
    ("tweets", "original_tweet_id TEXT"),
    ("tweets", "original_author_handle TEXT"),
    ("tweets", "original_author_name TEXT"),
    ("tweets", "original_content TEXT"),
    ("tweets", "is_x_article INTEGER DEFAULT 0"),
    ("tweets", "article_title TEXT"),
    ("tweets", "article_preview TEXT"),
    ("tweets", "article_text TEXT"),
    ("tweets", "article_summary_short TEXT"),
    ("tweets", "article_primary_points_json TEXT"),
    ("tweets", "article_action_items_json TEXT"),
    ("tweets", "article_top_visual_json TEXT"),
    ("tweets", "article_processed_at TIMESTAMP"),
    ("tweets", "links_json TEXT"),
    ("tweets", "in_reply_to_tweet_id TEXT"),
    ("tweets", "conversation_id TEXT"),
    ("tweets", "links_expanded_at TIMESTAMP"),
    ("tweets", "quote_reprocessed_at TIMESTAMP"),
    # accounts table columns
    ("accounts", "last_fetched_at TIMESTAMP"),
]

# SQL statements that are safe to run idempotently (CREATE IF NOT EXISTS)
_IDEMPOTENT_SQL_V1: list[str] = [
    # alert_log table
    """CREATE TABLE IF NOT EXISTS alert_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tweet_id TEXT,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        chat_id TEXT,
        FOREIGN KEY (tweet_id) REFERENCES tweets(id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_alert_log_sent ON alert_log(sent_at DESC)",
    # Performance indexes
    (
        "CREATE INDEX IF NOT EXISTS idx_tweets_processed_score "
        "ON tweets(processed_at, relevance_score DESC, created_at DESC)"
    ),
    "CREATE INDEX IF NOT EXISTS idx_tweets_author ON tweets(author_handle)",
    "CREATE INDEX IF NOT EXISTS idx_tweets_signal_tier ON tweets(signal_tier)",
    "CREATE INDEX IF NOT EXISTS idx_tweets_bookmarked ON tweets(bookmarked) WHERE bookmarked = 1",
    ("CREATE INDEX IF NOT EXISTS idx_tweets_quote ON tweets(quote_tweet_id) WHERE quote_tweet_id IS NOT NULL"),
    (
        "CREATE INDEX IF NOT EXISTS idx_tweets_reply "
        "ON tweets(in_reply_to_tweet_id) WHERE in_reply_to_tweet_id IS NOT NULL"
    ),
    "CREATE INDEX IF NOT EXISTS idx_fetch_log_endpoint ON fetch_log(endpoint, executed_at DESC)",
    # Metrics table
    """CREATE TABLE IF NOT EXISTS metrics (
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        value REAL NOT NULL,
        labels_json TEXT,
        recorded_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name, recorded_at DESC)",
]


def _safe_alter(conn: sqlite3.Connection, table: str, column_def: str) -> None:
    """Add a column to a table, ignoring 'duplicate column' errors."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            raise


def _run_v1(conn: sqlite3.Connection) -> None:
    """Version 1: consolidate all existing ad-hoc migrations."""
    for table, col_def in _ALTER_COLUMNS_V1:
        _safe_alter(conn, table, col_def)

    for sql in _IDEMPOTENT_SQL_V1:
        conn.execute(sql)


# ---------------------------------------------------------------------------
# Registry: list of (version, description, callable)
# ---------------------------------------------------------------------------

MigrationEntry = tuple[int, str, Callable[[sqlite3.Connection], None]]

MIGRATIONS: list[MigrationEntry] = [
    (1, "Consolidate ad-hoc column additions, indexes, alert_log, and metrics table", _run_v1),
]

# The target version is the highest version in the registry
TARGET_VERSION: int = MIGRATIONS[-1][0] if MIGRATIONS else 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current PRAGMA user_version."""
    cursor = conn.execute("PRAGMA user_version")
    return cursor.fetchone()[0]


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Set PRAGMA user_version (not parameterized — SQLite limitation)."""
    conn.execute(f"PRAGMA user_version = {int(version)}")


def run_migrations(conn: sqlite3.Connection) -> int:
    """Run all pending migrations and return the new schema version.

    Migrations are executed in version order. After each migration the
    user_version is bumped so that a crash mid-sequence resumes correctly.
    """
    current = get_schema_version(conn)

    for version, description, fn in MIGRATIONS:
        if current >= version:
            continue
        log.info("Running migration v%d: %s", version, description)
        fn(conn)
        set_schema_version(conn, version)
        current = version

    return current


def check_schema(conn: sqlite3.Connection) -> dict:
    """Compare expected schema against live database.

    Returns a dict with keys:
    - version_current: int
    - version_target: int
    - version_ok: bool
    - missing_tables: list[str]
    - missing_columns: dict[str, list[str]]  (table -> column names)
    - ok: bool  (True if everything matches)
    """
    version_current = get_schema_version(conn)
    version_ok = version_current >= TARGET_VERSION

    # Expected tables (from SCHEMA + migrations)
    expected_tables = {
        "tweets",
        "accounts",
        "narratives",
        "tweet_narratives",
        "fetch_log",
        "reactions",
        "prompts",
        "prompt_history",
        "context_commands",
        "alert_log",
        "metrics",
    }

    # Get actual tables
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    actual_tables = {row[0] for row in cursor.fetchall()}
    # Exclude FTS internal tables
    actual_tables = {t for t in actual_tables if not t.startswith("tweets_fts")}

    missing_tables = sorted(expected_tables - actual_tables)

    # Expected columns per table (only check tables that exist)
    expected_columns: dict[str, set[str]] = {
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
    }

    missing_columns: dict[str, list[str]] = {}
    for table, cols in expected_columns.items():
        if table in actual_tables:
            cursor = conn.execute(f"PRAGMA table_info({table})")
            actual_cols = {row[1] for row in cursor.fetchall()}
            missing = sorted(cols - actual_cols)
            if missing:
                missing_columns[table] = missing

    ok = version_ok and not missing_tables and not missing_columns

    return {
        "version_current": version_current,
        "version_target": TARGET_VERSION,
        "version_ok": version_ok,
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "ok": ok,
    }
