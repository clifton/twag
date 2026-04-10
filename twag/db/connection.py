"""Database connection management and initialization."""

import logging
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..config import get_database_path
from .schema import FTS_SCHEMA, SCHEMA

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
                conn.executescript(SCHEMA)
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


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run versioned schema migrations for existing databases."""
    from .migrations import run_pending_migrations
    from .prompts import seed_prompts

    # Apply versioned migrations
    run_pending_migrations(conn)

    # Initialize FTS5 if not present
    _init_fts(conn)

    # Seed prompts if table exists but is empty
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prompts'")
    if cursor.fetchone():
        seeded = seed_prompts(conn)
        if seeded > 0:
            conn.commit()


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
