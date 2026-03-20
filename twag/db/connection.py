"""Database connection management and initialization."""

import logging
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from ..config import get_database_path
from .schema import ACCOUNTS_COLUMNS, FTS_SCHEMA, SCHEMA, SCHEMA_VERSION, TWEETS_COLUMNS

log = logging.getLogger(__name__)


def init_db(db_path: Path | None = None) -> None:
    """Initialize the database with schema."""
    if db_path is None:
        db_path = get_database_path()

    db_path.parent.mkdir(parents=True, exist_ok=True)

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            with get_connection(db_path) as conn:
                conn.executescript(SCHEMA)
                _run_migrations(conn)
                _validate_schema(conn)
                conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_attempts - 1:
                time.sleep(1)
                continue
            raise


# ---------------------------------------------------------------------------
# Migration registry
# ---------------------------------------------------------------------------
# Each entry is (version, description, callable).  The callable receives a
# sqlite3.Connection and may execute arbitrary SQL.  Migrations whose version
# is <= the current PRAGMA user_version are skipped automatically.
#
# **Adding a new migration:**
#   1. Append a tuple here with version = SCHEMA_VERSION (after bumping it in
#      schema.py).
#   2. Bump SCHEMA_VERSION in schema.py.
#   3. Keep the migration idempotent (use IF NOT EXISTS / check columns).


def _migrate_v1_legacy_columns(conn: sqlite3.Connection) -> None:
    """Collapse all pre-versioning column additions into migration 1."""
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

    cursor = conn.execute("PRAGMA table_info(accounts)")
    account_columns = {row[1] for row in cursor.fetchall()}
    _add_columns_if_missing(conn, "accounts", account_columns, [("last_fetched_at", "TIMESTAMP")])


def _migrate_v2_indexes_fts_prompts(conn: sqlite3.Connection) -> None:
    """Ensure FTS, prompts, and performance indexes exist."""
    from .prompts import seed_prompts

    _init_fts(conn)

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prompts'")
    if cursor.fetchone():
        seeded = seed_prompts(conn)
        if seeded > 0:
            conn.commit()

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


MIGRATIONS: list[tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "legacy column additions", _migrate_v1_legacy_columns),
    (2, "indexes, FTS, and prompt seeding", _migrate_v2_indexes_fts_prompts),
]


def _add_columns_if_missing(
    conn: sqlite3.Connection,
    table: str,
    existing: set[str],
    columns: list[tuple[str, str]],
) -> None:
    for col_name, col_type in columns:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current PRAGMA user_version of the database."""
    cursor = conn.execute("PRAGMA user_version")
    return cursor.fetchone()[0]


def get_pending_migrations(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """Return list of (version, description) for migrations not yet applied."""
    current = get_schema_version(conn)
    return [(v, desc) for v, desc, _ in MIGRATIONS if v > current]


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run pending schema migrations and update user_version."""
    current = get_schema_version(conn)

    for version, description, migrate_fn in MIGRATIONS:
        if version <= current:
            continue
        log.info("Applying migration v%d: %s", version, description)
        migrate_fn(conn)
        conn.execute(f"PRAGMA user_version = {version}")

    # Ensure version is at least SCHEMA_VERSION even if no migrations ran
    if get_schema_version(conn) < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


# ---------------------------------------------------------------------------
# Schema drift detection
# ---------------------------------------------------------------------------


def _get_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def _validate_schema(conn: sqlite3.Connection) -> None:
    """Compare live DB columns against the expected constants and log drift."""
    for table, expected in [("tweets", TWEETS_COLUMNS), ("accounts", ACCOUNTS_COLUMNS)]:
        actual = _get_table_columns(conn, table)
        missing = expected - actual
        extra = actual - expected
        if missing:
            log.warning("Table %s is missing expected columns: %s", table, sorted(missing))
        if extra:
            log.warning("Table %s has columns not in schema constants: %s", table, sorted(extra))


def get_schema_drift(conn: sqlite3.Connection) -> dict[str, dict[str, set[str]]]:
    """Return drift info: {table: {missing: set, extra: set}} for each table."""
    result: dict[str, dict[str, set[str]]] = {}
    for table, expected in [("tweets", TWEETS_COLUMNS), ("accounts", ACCOUNTS_COLUMNS)]:
        actual = _get_table_columns(conn, table)
        missing = expected - actual
        extra = actual - expected
        if missing or extra:
            result[table] = {"missing": missing, "extra": extra}
    return result


# ---------------------------------------------------------------------------
# FTS helpers
# ---------------------------------------------------------------------------


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
