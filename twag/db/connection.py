"""Database connection management and initialization."""

import logging
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from ..config import get_database_path
from .schema import FTS_SCHEMA, LATEST_SCHEMA_VERSION, SCHEMA

log = logging.getLogger(__name__)
_LOCK_RETRY_ATTEMPTS = 4
_LOCK_RETRY_BASE_DELAY_SECONDS = 2.0


def init_db(db_path: Path | None = None) -> None:
    """Initialize the database with schema."""
    if db_path is None:
        db_path = get_database_path()

    db_path.parent.mkdir(parents=True, exist_ok=True)

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            with get_connection(db_path) as conn:
                # Detect fresh database before applying SCHEMA
                is_fresh = (
                    conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tweets'").fetchone()
                    is None
                )
                if not is_fresh:
                    # Legacy databases need columns added before SCHEMA indexes
                    _ensure_tables_exist(conn)
                    _migrate_v0_legacy(conn)
                conn.executescript(SCHEMA)
                if is_fresh:
                    _set_schema_version(conn, LATEST_SCHEMA_VERSION)
                _run_migrations(conn)
                conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_attempts - 1:
                time.sleep(1)
                continue
            raise


def _is_database_locked_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "database is locked" in message or "database table is locked" in message


def _with_lock_retry(operation: str, fn):
    delay = _LOCK_RETRY_BASE_DELAY_SECONDS
    for attempt in range(_LOCK_RETRY_ATTEMPTS):
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            if not _is_database_locked_error(exc) or attempt + 1 >= _LOCK_RETRY_ATTEMPTS:
                raise
            log.warning(
                "%s hit a locked database (attempt %d/%d); retrying in %.1fs",
                operation,
                attempt + 1,
                _LOCK_RETRY_ATTEMPTS,
                delay,
            )
            time.sleep(delay)
            delay *= 2


def execute_with_retry(conn: sqlite3.Connection, sql: str, params: tuple | list = ()):
    """Run ``conn.execute`` with retries when SQLite reports a transient lock."""
    return _with_lock_retry("sqlite execute", lambda: conn.execute(sql, params))


def executemany_with_retry(conn: sqlite3.Connection, sql: str, seq_of_params):
    """Run ``conn.executemany`` with retries when SQLite reports a transient lock."""
    cached_params = list(seq_of_params)
    return _with_lock_retry("sqlite executemany", lambda: conn.executemany(sql, cached_params))


def commit_with_retry(conn: sqlite3.Connection) -> None:
    """Commit with retries when SQLite reports a transient lock."""
    _with_lock_retry("sqlite commit", conn.commit)


def _ensure_tables_exist(conn: sqlite3.Connection) -> None:
    """Execute only CREATE TABLE statements from SCHEMA (skip indexes).

    This is needed before legacy migration so that new tables (like
    schema_version) exist, but index creation is deferred until after
    columns are added by the migration.
    """
    import re

    for stmt in SCHEMA.split(";"):
        stmt = stmt.strip()
        if re.match(r"CREATE\s+(TABLE|VIRTUAL\s+TABLE)", stmt, re.IGNORECASE):
            conn.execute(stmt)


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version, or 0 if untracked."""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
    if cursor.fetchone() is None:
        return 0
    row = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
    return row[0] if row else 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Set the schema version, creating the table if needed."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        "INSERT INTO schema_version (id, version, updated_at) VALUES (1, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(id) DO UPDATE SET version = excluded.version, updated_at = CURRENT_TIMESTAMP",
        (version,),
    )


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run schema migrations for existing databases.

    On a fresh database (schema_version table created by SCHEMA with latest
    version), this is a no-op beyond seeding prompts and FTS.  On a legacy
    database without schema_version, we run the legacy column-check migration
    first (v0 → v1), then apply any newer numbered migrations.
    """
    from .prompts import seed_prompts

    current = get_schema_version(conn)

    # Legacy database: no schema_version table yet
    if current == 0:
        _migrate_v0_legacy(conn)
        _set_schema_version(conn, 0)
        current = 0

    # Numbered migrations: each entry is (version, migrate_fn)
    migrations: list[tuple[int, Callable]] = [
        (1, _migrate_v1_narratives_unique),
    ]

    for version, migrate_fn in migrations:
        if current < version:
            log.info("Applying schema migration v%d", version)
            migrate_fn(conn)
            _set_schema_version(conn, version)
            current = version

    # Always ensure FTS and prompts are initialized (idempotent)
    _init_fts(conn)

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prompts'")
    if cursor.fetchone():
        seeded = seed_prompts(conn)
        if seeded > 0:
            conn.commit()


def _migrate_v0_legacy(conn: sqlite3.Connection) -> None:
    """Legacy migration: add columns and indexes that pre-versioned databases may lack."""
    # Check tweets table columns
    cursor = conn.execute("PRAGMA table_info(tweets)")
    tweet_columns = {row[1] for row in cursor.fetchall()}

    _add_columns_if_missing(
        conn,
        "tweets",
        tweet_columns,
        [
            ("bookmarked", "INTEGER DEFAULT 0"),
            ("bookmarked_at", "TIMESTAMP"),
            ("content_summary", "TEXT"),
            ("media_items", "TEXT"),
            ("analysis_json", "TEXT"),
            ("is_retweet", "INTEGER DEFAULT 0"),
            ("retweeted_by_handle", "TEXT"),
            ("retweeted_by_name", "TEXT"),
            ("original_tweet_id", "TEXT"),
            ("original_author_handle", "TEXT"),
            ("original_author_name", "TEXT"),
            ("original_content", "TEXT"),
            ("is_x_article", "INTEGER DEFAULT 0"),
            ("article_title", "TEXT"),
            ("article_preview", "TEXT"),
            ("article_text", "TEXT"),
            ("article_summary_short", "TEXT"),
            ("article_primary_points_json", "TEXT"),
            ("article_action_items_json", "TEXT"),
            ("article_top_visual_json", "TEXT"),
            ("article_processed_at", "TIMESTAMP"),
            ("links_json", "TEXT"),
            ("in_reply_to_tweet_id", "TEXT"),
            ("conversation_id", "TEXT"),
            ("links_expanded_at", "TIMESTAMP"),
            ("quote_reprocessed_at", "TIMESTAMP"),
        ],
    )

    # Check accounts table columns
    cursor = conn.execute("PRAGMA table_info(accounts)")
    account_columns = {row[1] for row in cursor.fetchall()}

    _add_columns_if_missing(
        conn,
        "accounts",
        account_columns,
        [("last_fetched_at", "TIMESTAMP")],
    )

    # Ensure indexes exist on legacy databases
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tweets_processed_score "
        "ON tweets(processed_at, relevance_score DESC, created_at DESC)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tweets_author ON tweets(author_handle)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tweets_signal_tier ON tweets(signal_tier)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tweets_bookmarked ON tweets(bookmarked) WHERE bookmarked = 1")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tweets_quote ON tweets(quote_tweet_id) WHERE quote_tweet_id IS NOT NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tweets_reply "
        "ON tweets(in_reply_to_tweet_id) WHERE in_reply_to_tweet_id IS NOT NULL"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fetch_log_endpoint ON fetch_log(endpoint, executed_at DESC)")


def _add_columns_if_missing(
    conn: sqlite3.Connection,
    table: str,
    existing: set[str],
    columns: list[tuple[str, str]],
) -> None:
    """Add columns to a table if they don't already exist."""
    for col_name, col_type in columns:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")


def _migrate_v1_narratives_unique(conn: sqlite3.Connection) -> None:
    """Add UNIQUE index on narratives.name for existing databases."""
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_narratives_name ON narratives(name)")


def _init_fts(conn: sqlite3.Connection) -> None:
    """Initialize FTS5 virtual table and triggers."""
    # Check if FTS table exists
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tweets_fts'")
    if cursor.fetchone() is not None:
        return  # Already initialized

    # Create FTS table and triggers
    conn.executescript(FTS_SCHEMA)

    # Backfill existing tweets into FTS
    conn.execute("""
        INSERT INTO tweets_fts(rowid, content, summary, author_handle, tickers)
        SELECT rowid, content, summary, author_handle, tickers
        FROM tweets
    """)


def rebuild_fts(conn: sqlite3.Connection) -> int:
    """Rebuild the FTS index from scratch. Returns number of rows indexed."""
    # Drop existing FTS table and triggers
    conn.execute("DROP TRIGGER IF EXISTS tweets_ai")
    conn.execute("DROP TRIGGER IF EXISTS tweets_ad")
    conn.execute("DROP TRIGGER IF EXISTS tweets_au")
    conn.execute("DROP TABLE IF EXISTS tweets_fts")

    # Recreate
    conn.executescript(FTS_SCHEMA)

    # Backfill
    cursor = conn.execute("""
        INSERT INTO tweets_fts(rowid, content, summary, author_handle, tickers)
        SELECT rowid, content, summary, author_handle, tickers
        FROM tweets
    """)
    return cursor.rowcount


@contextmanager
def get_connection(db_path: Path | None = None, readonly: bool = False) -> Iterator[sqlite3.Connection]:
    """Get a database connection with row factory.

    Args:
        db_path: Path to database file. If None, uses default from config.
        readonly: If True, open in readonly mode to avoid write locks.
    """
    if db_path is None:
        db_path = get_database_path()

    if readonly:
        # Open in readonly mode using URI syntax
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30)
    else:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")

    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
