"""Database connection management and initialization."""

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..config import get_database_path
from .schema import FTS_SCHEMA, SCHEMA


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
                conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_attempts - 1:
                time.sleep(1)
                continue
            raise


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run schema migrations for existing databases."""
    from .prompts import seed_prompts

    # Check tweets table columns
    cursor = conn.execute("PRAGMA table_info(tweets)")
    tweet_columns = {row[1] for row in cursor.fetchall()}

    if "bookmarked" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN bookmarked INTEGER DEFAULT 0")
        conn.execute("ALTER TABLE tweets ADD COLUMN bookmarked_at TIMESTAMP")

    if "content_summary" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN content_summary TEXT")

    if "media_items" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN media_items TEXT")

    if "analysis_json" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN analysis_json TEXT")

    if "is_retweet" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN is_retweet INTEGER DEFAULT 0")

    if "retweeted_by_handle" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN retweeted_by_handle TEXT")

    if "retweeted_by_name" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN retweeted_by_name TEXT")

    if "original_tweet_id" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN original_tweet_id TEXT")

    if "original_author_handle" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN original_author_handle TEXT")

    if "original_author_name" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN original_author_name TEXT")

    if "original_content" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN original_content TEXT")

    if "is_x_article" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN is_x_article INTEGER DEFAULT 0")

    if "article_title" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN article_title TEXT")

    if "article_preview" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN article_preview TEXT")

    if "article_text" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN article_text TEXT")

    if "article_summary_short" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN article_summary_short TEXT")

    if "article_primary_points_json" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN article_primary_points_json TEXT")

    if "article_action_items_json" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN article_action_items_json TEXT")

    if "article_top_visual_json" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN article_top_visual_json TEXT")

    if "article_processed_at" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN article_processed_at TIMESTAMP")

    if "links_json" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN links_json TEXT")

    if "in_reply_to_tweet_id" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN in_reply_to_tweet_id TEXT")

    if "conversation_id" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN conversation_id TEXT")

    if "links_expanded_at" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN links_expanded_at TIMESTAMP")

    if "quote_reprocessed_at" not in tweet_columns:
        conn.execute("ALTER TABLE tweets ADD COLUMN quote_reprocessed_at TIMESTAMP")

    # Check accounts table columns
    cursor = conn.execute("PRAGMA table_info(accounts)")
    account_columns = {row[1] for row in cursor.fetchall()}

    if "last_fetched_at" not in account_columns:
        conn.execute("ALTER TABLE accounts ADD COLUMN last_fetched_at TIMESTAMP")

    # Initialize FTS5 if not present
    _init_fts(conn)

    # Seed prompts if table exists but is empty
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prompts'")
    if cursor.fetchone():
        seeded = seed_prompts(conn)
        if seeded > 0:
            conn.commit()

    # Ensure performance indexes exist on existing databases
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
