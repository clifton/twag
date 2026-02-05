"""SQLite database models and queries for twag."""

import json
import re
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import get_database_path


# Eastern timezone offset (UTC-5, or UTC-4 during DST)
# We use a simple heuristic here; for production, consider using zoneinfo
def _get_et_offset() -> timedelta:
    """Get current Eastern Time offset from UTC (handles DST approximately)."""
    now = datetime.now(timezone.utc)
    # DST roughly runs from second Sunday in March to first Sunday in November
    year = now.year
    # March: second Sunday
    march_start = datetime(year, 3, 8, tzinfo=timezone.utc)
    while march_start.weekday() != 6:  # Sunday
        march_start += timedelta(days=1)
    # November: first Sunday
    nov_start = datetime(year, 11, 1, tzinfo=timezone.utc)
    while nov_start.weekday() != 6:
        nov_start += timedelta(days=1)

    if march_start <= now < nov_start:
        return timedelta(hours=-4)  # EDT
    return timedelta(hours=-5)  # EST


def get_market_day_cutoff() -> datetime:
    """
    Get the previous market close (4pm ET) as a UTC datetime.

    - Weekday before 4pm ET → previous business day's 4pm
    - Weekday after 4pm ET → same day's 4pm
    - Saturday → Friday 4pm
    - Sunday → Friday 4pm
    """
    et_offset = _get_et_offset()
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc + et_offset

    # Market close is 4pm ET (16:00)
    market_close_hour = 16

    # Start with today's date in ET
    today_et = now_et.date()
    weekday = today_et.weekday()  # 0=Monday, 6=Sunday

    # Determine the cutoff date
    if weekday == 5:  # Saturday
        cutoff_date = today_et - timedelta(days=1)  # Friday
    elif weekday == 6:  # Sunday
        cutoff_date = today_et - timedelta(days=2)  # Friday
    elif now_et.hour < market_close_hour:
        # Before 4pm on a weekday - use previous business day
        if weekday == 0:  # Monday
            cutoff_date = today_et - timedelta(days=3)  # Friday
        else:
            cutoff_date = today_et - timedelta(days=1)
    else:
        # After 4pm on a weekday - use today
        cutoff_date = today_et

    # Build the cutoff datetime (4pm ET on cutoff_date)
    cutoff_et = datetime(cutoff_date.year, cutoff_date.month, cutoff_date.day, market_close_hour, 0, 0)

    # Convert back to UTC
    cutoff_utc = cutoff_et - et_offset
    return cutoff_utc.replace(tzinfo=timezone.utc)


def parse_time_range(spec: str) -> tuple[datetime | None, datetime | None]:
    """
    Parse a time range specification.

    Supported formats:
    - "today" → since previous market close (4pm ET)
    - "7d", "24h", "1w" → relative durations
    - "2025-01-15" → specific date (full day)
    - "2025-01-15..2025-01-20" → date range

    Returns (since, until) as UTC datetimes.
    """
    spec = spec.strip().lower()
    now = datetime.now(timezone.utc)

    if spec == "today":
        return (get_market_day_cutoff(), None)

    # Relative duration: 7d, 24h, 1w
    duration_match = re.match(r"^(\d+)([hdwm])$", spec)
    if duration_match:
        amount = int(duration_match.group(1))
        unit = duration_match.group(2)

        if unit == "h":
            delta = timedelta(hours=amount)
        elif unit == "d":
            delta = timedelta(days=amount)
        elif unit == "w":
            delta = timedelta(weeks=amount)
        elif unit == "m":
            delta = timedelta(days=amount * 30)  # Approximate
        else:
            delta = timedelta(days=amount)

        return (now - delta, None)

    # Date range: YYYY-MM-DD..YYYY-MM-DD
    if ".." in spec:
        parts = spec.split("..")
        if len(parts) == 2:
            try:
                since = datetime.strptime(parts[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                until = datetime.strptime(parts[1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                # End of day for until
                until = until + timedelta(days=1)
                return (since, until)
            except ValueError:
                pass

    # Single date: YYYY-MM-DD
    try:
        date = datetime.strptime(spec, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (date, date + timedelta(days=1))
    except ValueError:
        pass

    return (None, None)


@dataclass
class SearchResult:
    """A tweet search result with relevance ranking."""

    id: str
    author_handle: str
    author_name: str | None
    content: str
    summary: str | None
    created_at: datetime | None
    relevance_score: float | None
    categories: list[str]
    signal_tier: str | None
    tickers: list[str]
    bookmarked: bool
    rank: float  # BM25 rank score (lower is more relevant)


SCHEMA = """
-- Tweets: Core storage with deduplication
CREATE TABLE IF NOT EXISTS tweets (
    id TEXT PRIMARY KEY,
    author_handle TEXT NOT NULL,
    author_name TEXT,
    content TEXT NOT NULL,
    created_at TIMESTAMP,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT,

    -- LLM processing results
    processed_at TIMESTAMP,
    relevance_score REAL,
    category TEXT,
    summary TEXT,
    content_summary TEXT,  -- Summarized content for long tweets
    signal_tier TEXT,
    tickers TEXT,
    analysis_json TEXT,

    -- Expansion tracking
    has_quote INTEGER DEFAULT 0,
    quote_tweet_id TEXT,
    has_media INTEGER DEFAULT 0,
    media_analysis TEXT,
    media_items TEXT,
    has_link INTEGER DEFAULT 0,
    link_summary TEXT,

    -- Output tracking
    included_in_digest TEXT,

    -- Bookmarks
    bookmarked INTEGER DEFAULT 0,
    bookmarked_at TIMESTAMP,

    FOREIGN KEY (quote_tweet_id) REFERENCES tweets(id)
);

-- Accounts: Tracking with boost/decay
CREATE TABLE IF NOT EXISTS accounts (
    handle TEXT PRIMARY KEY,
    display_name TEXT,
    tier INTEGER DEFAULT 2,
    weight REAL DEFAULT 50.0,
    category TEXT,

    -- Stats
    tweets_seen INTEGER DEFAULT 0,
    tweets_kept INTEGER DEFAULT 0,
    avg_relevance_score REAL,
    last_high_signal_at TIMESTAMP,
    last_fetched_at TIMESTAMP,

    -- Management
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    auto_promoted INTEGER DEFAULT 0,
    muted INTEGER DEFAULT 0
);

-- Narratives: Emerging theme tracking
CREATE TABLE IF NOT EXISTS narratives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_mentioned_at TIMESTAMP,
    mention_count INTEGER DEFAULT 1,
    sentiment TEXT,
    related_tickers TEXT,
    active INTEGER DEFAULT 1
);

-- Tweet-Narrative junction
CREATE TABLE IF NOT EXISTS tweet_narratives (
    tweet_id TEXT,
    narrative_id INTEGER,
    PRIMARY KEY (tweet_id, narrative_id),
    FOREIGN KEY (tweet_id) REFERENCES tweets(id),
    FOREIGN KEY (narrative_id) REFERENCES narratives(id)
);

-- Fetch history: Rate limit tracking
CREATE TABLE IF NOT EXISTS fetch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tweets_fetched INTEGER,
    new_tweets INTEGER,
    query_params TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tweets_created ON tweets(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tweets_score ON tweets(relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_tweets_unprocessed ON tweets(processed_at) WHERE processed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_accounts_tier ON accounts(tier, weight DESC);

-- User reactions for feedback loop
CREATE TABLE IF NOT EXISTS reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    reaction_type TEXT NOT NULL,  -- '>>', '>', '<', 'x_author', 'x_topic'
    reason TEXT,                   -- optional: why this should be rated differently
    target TEXT,                   -- author handle or category for X reactions
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tweet_id) REFERENCES tweets(id)
);

-- Editable prompts (extracted from scorer.py)
CREATE TABLE IF NOT EXISTS prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,     -- 'triage', 'batch_triage', 'enrichment', etc.
    template TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT                -- 'user' or 'llm'
);

-- Prompt history for rollback
CREATE TABLE IF NOT EXISTS prompt_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_name TEXT NOT NULL,
    template TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- CLI commands for context enrichment
CREATE TABLE IF NOT EXISTS context_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,      -- 'market_snapshot', 'ticker_price', etc.
    command_template TEXT NOT NULL, -- 'python scripts/market_at.py --date {tweet_date}'
    description TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Additional indexes for new tables
CREATE INDEX IF NOT EXISTS idx_reactions_tweet ON reactions(tweet_id);
CREATE INDEX IF NOT EXISTS idx_reactions_type ON reactions(reaction_type);
CREATE INDEX IF NOT EXISTS idx_prompt_history_name ON prompt_history(prompt_name, version DESC);
"""

# FTS5 schema for full-text search
FTS_SCHEMA = """
-- Full-text search virtual table
CREATE VIRTUAL TABLE IF NOT EXISTS tweets_fts USING fts5(
    content,
    summary,
    author_handle,
    tickers,
    content=tweets,
    content_rowid=rowid
);

-- Trigger to keep FTS in sync on INSERT
CREATE TRIGGER IF NOT EXISTS tweets_ai AFTER INSERT ON tweets BEGIN
    INSERT INTO tweets_fts(rowid, content, summary, author_handle, tickers)
    VALUES (NEW.rowid, NEW.content, NEW.summary, NEW.author_handle, NEW.tickers);
END;

-- Trigger to keep FTS in sync on DELETE
CREATE TRIGGER IF NOT EXISTS tweets_ad AFTER DELETE ON tweets BEGIN
    INSERT INTO tweets_fts(tweets_fts, rowid, content, summary, author_handle, tickers)
    VALUES ('delete', OLD.rowid, OLD.content, OLD.summary, OLD.author_handle, OLD.tickers);
END;

-- Trigger to keep FTS in sync on UPDATE
CREATE TRIGGER IF NOT EXISTS tweets_au AFTER UPDATE ON tweets BEGIN
    INSERT INTO tweets_fts(tweets_fts, rowid, content, summary, author_handle, tickers)
    VALUES ('delete', OLD.rowid, OLD.content, OLD.summary, OLD.author_handle, OLD.tickers);
    INSERT INTO tweets_fts(rowid, content, summary, author_handle, tickers)
    VALUES (NEW.rowid, NEW.content, NEW.summary, NEW.author_handle, NEW.tickers);
END;
"""


def init_db(db_path: Path | None = None) -> None:
    """Initialize the database with schema."""
    if db_path is None:
        db_path = get_database_path()

    db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)
        # Migrations for existing databases
        _run_migrations(conn)
        conn.commit()


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run schema migrations for existing databases."""
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
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Get a database connection with row factory."""
    if db_path is None:
        db_path = get_database_path()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# Tweet operations
def insert_tweet(
    conn: sqlite3.Connection,
    tweet_id: str,
    author_handle: str,
    content: str,
    created_at: datetime | None = None,
    author_name: str | None = None,
    source: str = "home",
    has_quote: bool = False,
    quote_tweet_id: str | None = None,
    has_media: bool = False,
    media_items: list[dict[str, Any]] | None = None,
    has_link: bool = False,
) -> bool:
    """Insert a tweet, returning True if new, False if duplicate."""
    try:
        conn.execute(
            """
            INSERT INTO tweets (
                id, author_handle, author_name, content, created_at, source,
                has_quote, quote_tweet_id, has_media, media_items, has_link
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tweet_id,
                author_handle,
                author_name,
                content,
                created_at.isoformat() if created_at else None,
                source,
                int(has_quote),
                quote_tweet_id,
                int(has_media),
                json.dumps(media_items) if media_items else None,
                int(has_link),
            ),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def get_unprocessed_tweets(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    """Get tweets that haven't been processed yet."""
    cursor = conn.execute(
        """
        SELECT * FROM tweets
        WHERE processed_at IS NULL
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    return cursor.fetchall()


def update_tweet_processing(
    conn: sqlite3.Connection,
    tweet_id: str,
    relevance_score: float,
    categories: list[str] | str,
    summary: str,
    signal_tier: str,
    tickers: list[str] | None = None,
) -> None:
    """Update a tweet with processing results."""
    # Normalize categories to list and store as JSON
    if isinstance(categories, str):
        categories = [categories]

    conn.execute(
        """
        UPDATE tweets SET
            processed_at = ?,
            relevance_score = ?,
            category = ?,
            summary = ?,
            signal_tier = ?,
            tickers = ?
        WHERE id = ?
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            relevance_score,
            json.dumps(categories),
            summary,
            signal_tier,
            json.dumps(tickers) if tickers else None,
            tweet_id,
        ),
    )


def update_tweet_enrichment(
    conn: sqlite3.Connection,
    tweet_id: str,
    media_analysis: str | None = None,
    media_items: list[dict[str, Any]] | None = None,
    link_summary: str | None = None,
    content_summary: str | None = None,
) -> None:
    """Update a tweet with enrichment data."""
    updates = []
    params = []

    if media_analysis is not None:
        updates.append("media_analysis = ?")
        params.append(media_analysis)

    if media_items is not None:
        updates.append("media_items = ?")
        params.append(json.dumps(media_items))

    if link_summary is not None:
        updates.append("link_summary = ?")
        params.append(link_summary)

    if content_summary is not None:
        updates.append("content_summary = ?")
        params.append(content_summary)

    if updates:
        params.append(tweet_id)
        conn.execute(
            f"UPDATE tweets SET {', '.join(updates)} WHERE id = ?",
            params,
        )


def update_tweet_analysis(
    conn: sqlite3.Connection,
    tweet_id: str,
    analysis: dict[str, Any],
    signal_tier: str | None = None,
    tickers: list[str] | None = None,
) -> None:
    """Store structured analysis results for a tweet."""
    updates = ["analysis_json = ?"]
    params: list[Any] = [json.dumps(analysis)]

    if signal_tier is not None:
        updates.append("signal_tier = ?")
        params.append(signal_tier)

    if tickers is not None:
        updates.append("tickers = ?")
        params.append(json.dumps(tickers) if tickers else None)

    params.append(tweet_id)
    conn.execute(
        f"UPDATE tweets SET {', '.join(updates)} WHERE id = ?",
        params,
    )


def get_tweets_for_digest(
    conn: sqlite3.Connection,
    date: str,
    min_score: float = 5.0,
) -> list[sqlite3.Row]:
    """Get processed tweets for a specific date above min_score."""
    cursor = conn.execute(
        """
        SELECT * FROM tweets
        WHERE date(created_at) = ?
        AND relevance_score >= ?
        AND processed_at IS NOT NULL
        ORDER BY relevance_score DESC
        """,
        (date, min_score),
    )
    return cursor.fetchall()


def mark_tweet_in_digest(conn: sqlite3.Connection, tweet_id: str, date: str) -> None:
    """Mark a tweet as included in a digest."""
    conn.execute(
        "UPDATE tweets SET included_in_digest = ? WHERE id = ?",
        (date, tweet_id),
    )


def is_tweet_seen(conn: sqlite3.Connection, tweet_id: str) -> bool:
    """Check if a tweet has been seen before."""
    cursor = conn.execute("SELECT 1 FROM tweets WHERE id = ?", (tweet_id,))
    return cursor.fetchone() is not None


def get_tweet_stats(conn: sqlite3.Connection, date: str | None = None) -> dict[str, Any]:
    """Get tweet processing statistics."""
    if date:
        where_clause = "WHERE date(created_at) = ?"
        params: tuple = (date,)
    else:
        where_clause = ""
        params = ()

    cursor = conn.execute(
        f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN processed_at IS NOT NULL THEN 1 ELSE 0 END) as processed,
            SUM(CASE WHEN processed_at IS NULL THEN 1 ELSE 0 END) as pending,
            AVG(relevance_score) as avg_score,
            SUM(CASE WHEN relevance_score >= 7 THEN 1 ELSE 0 END) as high_signal,
            SUM(CASE WHEN relevance_score >= 5 THEN 1 ELSE 0 END) as digest_worthy
        FROM tweets
        {where_clause}
        """,
        params,
    )
    row = cursor.fetchone()
    return dict(row) if row else {}


def get_processed_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Get counts of tweets processed in recent time windows.

    Returns:
        Dict with keys '1h', '24h', '7d' containing tweet counts.
    """
    cursor = conn.execute(
        """
        SELECT
            SUM(CASE WHEN processed_at >= datetime('now', '-1 hour') THEN 1 ELSE 0 END) as last_1h,
            SUM(CASE WHEN processed_at >= datetime('now', '-24 hours') THEN 1 ELSE 0 END) as last_24h,
            SUM(CASE WHEN processed_at >= datetime('now', '-7 days') THEN 1 ELSE 0 END) as last_7d
        FROM tweets
        WHERE processed_at IS NOT NULL
        """
    )
    row = cursor.fetchone()
    if row:
        return {
            "1h": row["last_1h"] or 0,
            "24h": row["last_24h"] or 0,
            "7d": row["last_7d"] or 0,
        }
    return {"1h": 0, "24h": 0, "7d": 0}


# Account operations
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


# Narrative operations
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


# Fetch log operations
def log_fetch(
    conn: sqlite3.Connection,
    endpoint: str,
    tweets_fetched: int,
    new_tweets: int,
    query_params: dict | None = None,
) -> None:
    """Log a fetch operation."""
    conn.execute(
        """
        INSERT INTO fetch_log (endpoint, tweets_fetched, new_tweets, query_params)
        VALUES (?, ?, ?, ?)
        """,
        (endpoint, tweets_fetched, new_tweets, json.dumps(query_params)),
    )


def get_last_fetch(conn: sqlite3.Connection, endpoint: str) -> sqlite3.Row | None:
    """Get the last fetch for an endpoint."""
    cursor = conn.execute(
        """
        SELECT * FROM fetch_log
        WHERE endpoint = ?
        ORDER BY executed_at DESC
        LIMIT 1
        """,
        (endpoint,),
    )
    return cursor.fetchone()


# Bookmark operations
def mark_tweet_bookmarked(conn: sqlite3.Connection, tweet_id: str) -> None:
    """Mark a tweet as bookmarked."""
    conn.execute(
        """
        UPDATE tweets SET
            bookmarked = 1,
            bookmarked_at = COALESCE(bookmarked_at, ?)
        WHERE id = ?
        """,
        (datetime.now(timezone.utc).isoformat(), tweet_id),
    )


def get_bookmark_counts_by_author(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Get count of bookmarked tweets per author."""
    cursor = conn.execute(
        """
        SELECT author_handle, COUNT(*) as bookmark_count
        FROM tweets
        WHERE bookmarked = 1
        GROUP BY author_handle
        ORDER BY bookmark_count DESC
        """
    )
    return [(row[0], row[1]) for row in cursor.fetchall()]


def get_authors_to_promote(conn: sqlite3.Connection, min_bookmarks: int = 3) -> list[str]:
    """Get authors with enough bookmarks to promote to tier-1."""
    cursor = conn.execute(
        """
        SELECT t.author_handle
        FROM tweets t
        LEFT JOIN accounts a ON t.author_handle = a.handle
        WHERE t.bookmarked = 1
        AND (a.tier IS NULL OR a.tier > 1)
        GROUP BY t.author_handle
        HAVING COUNT(*) >= ?
        """,
        (min_bookmarks,),
    )
    return [row[0] for row in cursor.fetchall()]


# Migration helper
def migrate_seen_json(conn: sqlite3.Connection, seen_json_path: Path) -> int:
    """Migrate seen.json to database. Returns count of migrated IDs."""
    if not seen_json_path.exists():
        return 0

    with open(seen_json_path) as f:
        data = json.load(f)

    seen_ids = data.get("seen", [])
    count = 0

    for tweet_id in seen_ids:
        try:
            conn.execute(
                """
                INSERT INTO tweets (id, author_handle, content, source)
                VALUES (?, ?, ?, ?)
                """,
                (tweet_id, "unknown", "[migrated from seen.json]", "migration"),
            )
            count += 1
        except sqlite3.IntegrityError:
            pass  # Already exists

    return count


# Maintenance operations
def prune_old_tweets(conn: sqlite3.Connection, days: int = 14) -> int:
    """Delete tweets older than specified days. Returns count deleted."""
    cursor = conn.execute(
        """
        DELETE FROM tweets
        WHERE created_at < datetime('now', ?)
        AND included_in_digest IS NOT NULL
        """,
        (f"-{days} days",),
    )
    return cursor.rowcount


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


# Full-text search operations
def search_tweets(
    conn: sqlite3.Connection,
    query: str,
    *,
    category: str | None = None,
    author: str | None = None,
    min_score: float | None = None,
    signal_tier: str | None = None,
    ticker: str | None = None,
    bookmarked_only: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
    time_range: str | None = None,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "rank",
) -> list[SearchResult]:
    """
    Search tweets using FTS5 full-text search.

    Args:
        query: FTS5 query string (supports AND, OR, NOT, phrases, prefixes)
        category: Filter by category (fed_policy, equities, etc.)
        author: Filter by author handle
        min_score: Minimum relevance score
        signal_tier: Filter by signal tier
        ticker: Filter by ticker symbol
        bookmarked_only: Only return bookmarked tweets
        since: Start time (UTC datetime)
        until: End time (UTC datetime)
        time_range: Time range spec ("today", "7d", "2025-01-15", etc.)
        limit: Maximum results to return
        offset: Offset for pagination
        order_by: Sort order - "rank" (BM25), "score" (relevance), "time" (created_at)

    Returns:
        List of SearchResult objects
    """
    # Parse time_range if provided
    if time_range:
        parsed_since, parsed_until = parse_time_range(time_range)
        if parsed_since and since is None:
            since = parsed_since
        if parsed_until and until is None:
            until = parsed_until

    # Build WHERE conditions
    conditions = []
    params: list[Any] = []

    # FTS match
    conditions.append("tweets_fts MATCH ?")
    params.append(query)

    if category:
        # Match category in JSON array (e.g., '["fed_policy", "rates_fx"]')
        # Also support legacy single-value format
        conditions.append("(t.category LIKE ? OR t.category = ?)")
        params.append(f'%"{category}"%')
        params.append(category)

    if author:
        conditions.append("t.author_handle = ?")
        params.append(author.lstrip("@"))

    if min_score is not None:
        conditions.append("t.relevance_score >= ?")
        params.append(min_score)

    if signal_tier:
        conditions.append("t.signal_tier = ?")
        params.append(signal_tier)

    if ticker:
        # Search in JSON array or comma-separated string
        conditions.append("(t.tickers LIKE ? OR t.tickers LIKE ?)")
        params.append(f'%"{ticker.upper()}"%')
        params.append(f"%{ticker.upper()}%")

    if bookmarked_only:
        conditions.append("t.bookmarked = 1")

    if since:
        conditions.append("t.created_at >= ?")
        params.append(since.isoformat())

    if until:
        conditions.append("t.created_at < ?")
        params.append(until.isoformat())

    where_clause = " AND ".join(conditions)

    # Order clause
    if order_by == "score":
        order_clause = "t.relevance_score DESC NULLS LAST"
    elif order_by == "time":
        order_clause = "t.created_at DESC"
    else:  # rank (BM25)
        order_clause = "bm25(tweets_fts)"

    params.extend([limit, offset])

    sql = f"""
        SELECT
            t.id,
            t.author_handle,
            t.author_name,
            t.content,
            t.summary,
            t.created_at,
            t.relevance_score,
            t.category,
            t.signal_tier,
            t.tickers,
            t.bookmarked,
            bm25(tweets_fts) as rank
        FROM tweets_fts
        JOIN tweets t ON tweets_fts.rowid = t.rowid
        WHERE {where_clause}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """

    cursor = conn.execute(sql, params)
    results = []

    for row in cursor.fetchall():
        # Parse tickers from JSON or comma-separated
        tickers_raw = row["tickers"]
        if tickers_raw:
            try:
                tickers = json.loads(tickers_raw)
            except json.JSONDecodeError:
                tickers = [t.strip() for t in tickers_raw.split(",") if t.strip()]
        else:
            tickers = []

        # Parse created_at
        created_at = None
        if row["created_at"]:
            try:
                created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            except ValueError:
                pass

        # Parse categories from JSON array or legacy string
        categories_raw = row["category"]
        if categories_raw:
            try:
                categories = json.loads(categories_raw)
                if isinstance(categories, str):
                    categories = [categories]
            except json.JSONDecodeError:
                categories = [categories_raw]
        else:
            categories = []

        results.append(
            SearchResult(
                id=row["id"],
                author_handle=row["author_handle"],
                author_name=row["author_name"],
                content=row["content"],
                summary=row["summary"],
                created_at=created_at,
                relevance_score=row["relevance_score"],
                categories=categories,
                signal_tier=row["signal_tier"],
                tickers=tickers,
                bookmarked=bool(row["bookmarked"]),
                rank=row["rank"],
            )
        )

    return results


# Keywords that suggest equity-relevant context (for auto-today default)
EQUITY_KEYWORDS = {
    "earnings",
    "eps",
    "revenue",
    "guidance",
    "beat",
    "miss",
    "upgrade",
    "downgrade",
    "buy",
    "sell",
    "target",
    "pt",
    "q1",
    "q2",
    "q3",
    "q4",
    "quarterly",
    "results",
    "report",
}


def query_suggests_equity_context(query: str) -> bool:
    """Check if a search query suggests equity-relevant context."""
    query_lower = query.lower()
    return any(kw in query_lower for kw in EQUITY_KEYWORDS)


# ============================================================================
# Reaction operations (for feedback loop)
# ============================================================================


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


# ============================================================================
# Prompt operations (for editable LLM prompts)
# ============================================================================


@dataclass
class Prompt:
    """An editable LLM prompt template."""

    id: int
    name: str
    template: str
    version: int
    updated_at: datetime | None
    updated_by: str | None


def get_prompt(conn: sqlite3.Connection, name: str) -> Prompt | None:
    """Get a prompt by name."""
    cursor = conn.execute(
        "SELECT * FROM prompts WHERE name = ?",
        (name,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    updated_at = None
    if row["updated_at"]:
        try:
            updated_at = datetime.fromisoformat(row["updated_at"])
        except ValueError:
            pass

    return Prompt(
        id=row["id"],
        name=row["name"],
        template=row["template"],
        version=row["version"],
        updated_at=updated_at,
        updated_by=row["updated_by"],
    )


def get_all_prompts(conn: sqlite3.Connection) -> list[Prompt]:
    """Get all prompts."""
    cursor = conn.execute("SELECT * FROM prompts ORDER BY name")
    results = []
    for row in cursor.fetchall():
        updated_at = None
        if row["updated_at"]:
            try:
                updated_at = datetime.fromisoformat(row["updated_at"])
            except ValueError:
                pass
        results.append(
            Prompt(
                id=row["id"],
                name=row["name"],
                template=row["template"],
                version=row["version"],
                updated_at=updated_at,
                updated_by=row["updated_by"],
            )
        )
    return results


def upsert_prompt(
    conn: sqlite3.Connection,
    name: str,
    template: str,
    updated_by: str = "user",
) -> int:
    """Insert or update a prompt. Returns new version number."""
    # Get current version if exists
    cursor = conn.execute("SELECT version, template FROM prompts WHERE name = ?", (name,))
    row = cursor.fetchone()

    if row:
        old_version = row["version"]
        old_template = row["template"]

        # Save to history before updating
        conn.execute(
            """
            INSERT INTO prompt_history (prompt_name, template, version)
            VALUES (?, ?, ?)
            """,
            (name, old_template, old_version),
        )

        new_version = old_version + 1
        conn.execute(
            """
            UPDATE prompts SET
                template = ?,
                version = ?,
                updated_at = ?,
                updated_by = ?
            WHERE name = ?
            """,
            (template, new_version, datetime.now(timezone.utc).isoformat(), updated_by, name),
        )
        return new_version
    else:
        conn.execute(
            """
            INSERT INTO prompts (name, template, version, updated_at, updated_by)
            VALUES (?, ?, 1, ?, ?)
            """,
            (name, template, datetime.now(timezone.utc).isoformat(), updated_by),
        )
        return 1


def get_prompt_history(conn: sqlite3.Connection, name: str, limit: int = 10) -> list[dict[str, Any]]:
    """Get version history for a prompt."""
    cursor = conn.execute(
        """
        SELECT * FROM prompt_history
        WHERE prompt_name = ?
        ORDER BY version DESC
        LIMIT ?
        """,
        (name, limit),
    )
    return [dict(row) for row in cursor.fetchall()]


def rollback_prompt(conn: sqlite3.Connection, name: str, to_version: int) -> bool:
    """Rollback a prompt to a specific version. Returns True if successful."""
    cursor = conn.execute(
        """
        SELECT template FROM prompt_history
        WHERE prompt_name = ? AND version = ?
        """,
        (name, to_version),
    )
    row = cursor.fetchone()
    if not row:
        return False

    upsert_prompt(conn, name, row["template"], updated_by="rollback")
    return True


# Default prompts to seed from scorer.py
DEFAULT_PROMPTS = {
    "triage": """You are a financial markets triage agent. Score this tweet 0-10 for relevance to macro/investing.

Categories (assign 1-3 that apply): fed_policy, inflation, job_market, macro_data, earnings, equities, rates_fx, credit, banks, consumer_spending, capex, commodities, energy, metals_mining, geopolitical, sanctions, tech_business, ai_advancement, crypto, noise

Tweet: {tweet_text}
Author: @{handle}

Return JSON only:
{{"score": 7, "categories": ["fed_policy", "rates_fx"], "summary": "One-liner summary", "tickers": ["TLT", "GLD"]}}""",
    "batch_triage": """You are a financial markets triage agent. Score these tweets 0-10 for relevance to macro/investing.

Categories (assign 1-3 that apply): fed_policy, inflation, job_market, macro_data, earnings, equities, rates_fx, credit, banks, consumer_spending, capex, commodities, energy, metals_mining, geopolitical, sanctions, tech_business, ai_advancement, crypto, noise

Tweets:
{tweets}

Return a JSON array with one object per tweet, in order:
[{{"id": "tweet_id", "score": 7, "categories": ["fed_policy", "rates_fx"], "summary": "One-liner", "tickers": ["TLT"]}}]""",
    "enrichment": """You are a financial analyst. Analyze this tweet for actionable insights.

Tweet: {tweet_text}
Author: @{handle} ({author_category})
Quoted: {quoted_tweet}
Linked article: {article_summary}
Media context: {image_description}

Provide:
1. Signal tier: high_signal | market_relevant | news | noise
2. Key insight (1-2 sentences)
3. Investment implications with specific tickers
4. Any emerging narratives this connects to

Return JSON:
{{"signal_tier": "high_signal", "insight": "...", "implications": "...", "narratives": ["Fed pivot"], "tickers": ["TLT"]}}""",
    "summarize": """Summarize this tweet concisely while preserving all key market-relevant information, data points, and actionable insights. Keep ticker symbols and specific numbers.

Tweet by @{handle}:
{tweet_text}

Provide a summary in 2-4 sentences (under 400 characters). Return only the summary text, no JSON.""",
    "vision": """Analyze this image from a financial Twitter post.

Determine if it is a chart, a document/screen with coherent prose, or a meme/photo/other.

Return JSON:
{
  "kind": "chart|document|screenshot|meme|photo|other",
  "short_description": "very short description (3-8 words)",
  "prose_text": "FULL text if it's coherent prose; otherwise empty string",
  "prose_summary": "short summary if prose; otherwise empty string",
  "chart": {
    "type": "line|bar|candlestick|heatmap|table|other",
    "description": "what data is shown",
    "insight": "key visual insight",
    "implication": "investment implication",
    "tickers": ["AAPL"]
  }
}

Rules:
- If NOT a chart, set chart fields to empty strings and [].
- If there is not coherent prose, set prose_text to "".
- If prose_text is provided, preserve paragraphs and wording as written.
- short_description should be very short and neutral.
""",
}


def seed_prompts(conn: sqlite3.Connection) -> int:
    """Seed default prompts if they don't exist. Returns count of seeded prompts."""
    count = 0
    for name, template in DEFAULT_PROMPTS.items():
        cursor = conn.execute("SELECT 1 FROM prompts WHERE name = ?", (name,))
        if not cursor.fetchone():
            conn.execute(
                """
                INSERT INTO prompts (name, template, version, updated_at, updated_by)
                VALUES (?, ?, 1, ?, 'seed')
                """,
                (name, template, datetime.now(timezone.utc).isoformat()),
            )
            count += 1
    return count


# ============================================================================
# Context command operations (for CLI-based context enrichment)
# ============================================================================


@dataclass
class ContextCommand:
    """A CLI command for fetching context during analysis."""

    id: int
    name: str
    command_template: str
    description: str | None
    enabled: bool
    created_at: datetime | None


def get_context_command(conn: sqlite3.Connection, name: str) -> ContextCommand | None:
    """Get a context command by name."""
    cursor = conn.execute(
        "SELECT * FROM context_commands WHERE name = ?",
        (name,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    created_at = None
    if row["created_at"]:
        try:
            created_at = datetime.fromisoformat(row["created_at"])
        except ValueError:
            pass

    return ContextCommand(
        id=row["id"],
        name=row["name"],
        command_template=row["command_template"],
        description=row["description"],
        enabled=bool(row["enabled"]),
        created_at=created_at,
    )


def get_all_context_commands(conn: sqlite3.Connection, enabled_only: bool = False) -> list[ContextCommand]:
    """Get all context commands."""
    if enabled_only:
        cursor = conn.execute("SELECT * FROM context_commands WHERE enabled = 1 ORDER BY name")
    else:
        cursor = conn.execute("SELECT * FROM context_commands ORDER BY name")

    results = []
    for row in cursor.fetchall():
        created_at = None
        if row["created_at"]:
            try:
                created_at = datetime.fromisoformat(row["created_at"])
            except ValueError:
                pass
        results.append(
            ContextCommand(
                id=row["id"],
                name=row["name"],
                command_template=row["command_template"],
                description=row["description"],
                enabled=bool(row["enabled"]),
                created_at=created_at,
            )
        )
    return results


def upsert_context_command(
    conn: sqlite3.Connection,
    name: str,
    command_template: str,
    description: str | None = None,
    enabled: bool = True,
) -> int:
    """Insert or update a context command. Returns command ID."""
    cursor = conn.execute(
        """
        INSERT INTO context_commands (name, command_template, description, enabled)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            command_template = excluded.command_template,
            description = COALESCE(excluded.description, description),
            enabled = excluded.enabled
        RETURNING id
        """,
        (name, command_template, description, int(enabled)),
    )
    row = cursor.fetchone()
    return row[0] if row else 0


def delete_context_command(conn: sqlite3.Connection, name: str) -> bool:
    """Delete a context command. Returns True if deleted."""
    cursor = conn.execute("DELETE FROM context_commands WHERE name = ?", (name,))
    return cursor.rowcount > 0


def toggle_context_command(conn: sqlite3.Connection, name: str, enabled: bool) -> bool:
    """Enable or disable a context command. Returns True if found."""
    cursor = conn.execute(
        "UPDATE context_commands SET enabled = ? WHERE name = ?",
        (int(enabled), name),
    )
    return cursor.rowcount > 0


# ============================================================================
# Web feed operations
# ============================================================================


@dataclass
class FeedTweet:
    """A tweet for the web feed with all display fields."""

    id: str
    author_handle: str
    author_name: str | None
    content: str
    content_summary: str | None
    summary: str | None
    created_at: datetime | None
    relevance_score: float | None
    categories: list[str]
    signal_tier: str | None
    tickers: list[str]
    bookmarked: bool
    has_quote: bool
    quote_tweet_id: str | None
    has_media: bool
    media_analysis: str | None
    media_items: list[dict[str, Any]]
    has_link: bool
    link_summary: str | None
    reactions: list[str]  # Reaction types for this tweet


def get_feed_tweets(
    conn: sqlite3.Connection,
    *,
    category: str | None = None,
    ticker: str | None = None,
    min_score: float | None = None,
    signal_tier: str | None = None,
    author: str | None = None,
    bookmarked_only: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
    order_by: str = "relevance",
    limit: int = 50,
    offset: int = 0,
) -> list[FeedTweet]:
    """Get tweets for the web feed with filters."""
    conditions = ["t.processed_at IS NOT NULL"]
    params: list[Any] = []

    if category:
        conditions.append("(t.category LIKE ? OR t.category = ?)")
        params.append(f'%"{category}"%')
        params.append(category)

    if ticker:
        conditions.append("(t.tickers LIKE ? OR t.tickers LIKE ?)")
        params.append(f'%"{ticker.upper()}"%')
        params.append(f"%{ticker.upper()}%")

    if min_score is not None:
        conditions.append("t.relevance_score >= ?")
        params.append(min_score)

    if signal_tier:
        conditions.append("t.signal_tier = ?")
        params.append(signal_tier)

    if author:
        conditions.append("t.author_handle = ?")
        params.append(author.lstrip("@"))

    if bookmarked_only:
        conditions.append("t.bookmarked = 1")

    if since:
        conditions.append("t.created_at >= ?")
        params.append(since.isoformat())

    if until:
        conditions.append("t.created_at < ?")
        params.append(until.isoformat())

    where_clause = " AND ".join(conditions)
    params.extend([limit, offset])

    if order_by == "latest":
        order_clause = "t.created_at DESC"
    else:
        order_clause = "t.relevance_score DESC, t.created_at DESC"

    cursor = conn.execute(
        f"""
        SELECT
            t.*,
            GROUP_CONCAT(DISTINCT r.reaction_type) as reaction_types
        FROM tweets t
        LEFT JOIN reactions r ON t.id = r.tweet_id
        WHERE {where_clause}
        GROUP BY t.id
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
        """,
        params,
    )

    results = []
    for row in cursor.fetchall():
        # Parse categories
        categories_raw = row["category"]
        if categories_raw:
            try:
                categories = json.loads(categories_raw)
                if isinstance(categories, str):
                    categories = [categories]
            except json.JSONDecodeError:
                categories = [categories_raw]
        else:
            categories = []

        # Parse tickers
        tickers_raw = row["tickers"]
        if tickers_raw:
            try:
                tickers = json.loads(tickers_raw)
            except json.JSONDecodeError:
                tickers = [t.strip() for t in tickers_raw.split(",") if t.strip()]
        else:
            tickers = []

        # Parse created_at
        created_at = None
        if row["created_at"]:
            try:
                created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            except ValueError:
                pass

        # Parse reactions
        reactions = []
        if row["reaction_types"]:
            reactions = row["reaction_types"].split(",")

        # Parse media items
        media_items = []
        if row["media_items"]:
            try:
                media_items = json.loads(row["media_items"])
            except json.JSONDecodeError:
                media_items = []

        results.append(
            FeedTweet(
                id=row["id"],
                author_handle=row["author_handle"],
                author_name=row["author_name"],
                content=row["content"],
                content_summary=row["content_summary"],
                summary=row["summary"],
                created_at=created_at,
                relevance_score=row["relevance_score"],
                categories=categories,
                signal_tier=row["signal_tier"],
                tickers=tickers,
                bookmarked=bool(row["bookmarked"]),
                has_quote=bool(row["has_quote"]),
                quote_tweet_id=row["quote_tweet_id"],
                has_media=bool(row["has_media"]),
                media_analysis=row["media_analysis"],
                media_items=media_items,
                has_link=bool(row["has_link"]),
                link_summary=row["link_summary"],
                reactions=reactions,
            )
        )

    return results


# ============================================================================
# Dump and restore operations
# ============================================================================

# FTS shadow table suffixes and related object names to filter during dump
_FTS_TABLE = "tweets_fts"
_FTS_SHADOW_SUFFIXES = ("_config", "_content", "_data", "_docsize", "_idx")
_FTS_TRIGGERS = ("tweets_ai", "tweets_ad", "tweets_au")


def _is_fts_statement(stmt: str) -> bool:
    """Check if a SQL statement is FTS-related and should be skipped during dump."""
    # PRAGMA writable_schema (used by iterdump for virtual tables)
    if "PRAGMA writable_schema" in stmt:
        return True
    # INSERT INTO sqlite_master (iterdump hack for virtual tables)
    if "INSERT INTO sqlite_master" in stmt:
        return True
    # Direct references to the FTS table or its shadow tables
    if _FTS_TABLE in stmt:
        return True
    for suffix in _FTS_SHADOW_SUFFIXES:
        if f"{_FTS_TABLE}{suffix}" in stmt:
            return True
    # FTS sync triggers
    return any(trigger in stmt for trigger in _FTS_TRIGGERS)


def _filter_fts_from_sql(sql: str) -> str:
    """Filter FTS-related statements from a SQL dump string.

    Handles multi-line statements (CREATE TABLE, CREATE TRIGGER) by tracking
    nesting depth. Statements starting with CREATE TRIGGER or CREATE TABLE
    may contain embedded semicolons, so we look for the final semicolon at
    the top level.
    """
    output_lines = []
    current_stmt_lines: list[str] = []
    in_block = False  # Inside a CREATE TRIGGER / multi-line block

    for line in sql.splitlines():
        stripped = line.strip()
        current_stmt_lines.append(line)

        # Detect start of block statements (CREATE TRIGGER has BEGIN...END)
        if not in_block and re.match(r"CREATE\s+TRIGGER\b", stripped, re.IGNORECASE):
            in_block = True

        # Check for statement terminator
        if stripped.endswith(";"):
            if in_block:
                # For triggers, the statement ends at "END;"
                if stripped.upper() == "END;":
                    # Complete trigger statement accumulated
                    full_stmt = "\n".join(current_stmt_lines)
                    if not _is_fts_statement(full_stmt):
                        output_lines.extend(current_stmt_lines)
                    current_stmt_lines = []
                    in_block = False
                # else: semicolon inside trigger body, keep accumulating
            else:
                # Normal statement (single or multi-line like CREATE TABLE)
                full_stmt = "\n".join(current_stmt_lines)
                if not _is_fts_statement(full_stmt):
                    output_lines.extend(current_stmt_lines)
                current_stmt_lines = []

    # Any remaining lines (shouldn't happen with well-formed SQL)
    if current_stmt_lines:
        full_stmt = "\n".join(current_stmt_lines)
        if not _is_fts_statement(full_stmt):
            output_lines.extend(current_stmt_lines)

    return "\n".join(output_lines)


def dump_sql(db_path: Path | None = None) -> Iterator[str]:
    """Dump database to clean SQL statements, filtering out FTS5 artifacts.

    iterdump() produces broken output for FTS5 virtual tables (PRAGMA
    writable_schema, INSERT INTO sqlite_master, shadow table CREATE
    statements). Since the FTS index is content-synced and can be rebuilt
    from the tweets table, we simply skip all FTS-related statements.

    Args:
        db_path: Path to the database file. Uses default if None.

    Yields:
        Clean SQL statements suitable for executescript().
    """
    if db_path is None:
        db_path = get_database_path()

    conn = sqlite3.connect(db_path)
    try:
        for stmt in conn.iterdump():
            if not _is_fts_statement(stmt):
                yield stmt
    finally:
        conn.close()


def restore_sql(
    sql: str,
    db_path: Path | None = None,
    backup: bool = True,
) -> dict[str, int]:
    """Restore a database from a SQL dump string.

    Handles dumps that may contain FTS5 shadow table statements (legacy
    dumps) by filtering them out before executing. After restore, rebuilds
    the FTS index from the tweets table.

    Args:
        sql: The SQL dump content to restore.
        db_path: Path for the restored database. Uses default if None.
        backup: If True, backs up existing db to .db.bak before replacing.

    Returns:
        Dict with counts: {"tweets": N, "accounts": N, "fts": N}
    """
    if db_path is None:
        db_path = get_database_path()

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Backup existing database
    if backup and db_path.exists():
        backup_path = db_path.with_suffix(".db.bak")
        shutil.copy2(db_path, backup_path)

    # Remove existing database
    if db_path.exists():
        db_path.unlink()

    # Filter out FTS-related statements from the SQL dump.
    # Legacy dumps from iterdump() contain multi-line statements (e.g.
    # CREATE TRIGGER with embedded semicolons). We accumulate lines into
    # complete statements, then check each whole statement for FTS refs.
    filtered_sql = _filter_fts_from_sql(sql)

    # Execute the filtered SQL
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(filtered_sql)
        conn.commit()

        # Rebuild FTS index from tweets table
        fts_count = rebuild_fts(conn)
        conn.commit()

        # Get counts for verification
        tweet_count = conn.execute("SELECT COUNT(*) FROM tweets").fetchone()[0]
        account_count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]

        return {"tweets": tweet_count, "accounts": account_count, "fts": fts_count}
    except Exception:
        conn.close()
        # Attempt to restore backup on failure
        if backup:
            backup_path = db_path.with_suffix(".db.bak")
            if backup_path.exists():
                if db_path.exists():
                    db_path.unlink()
                shutil.copy2(backup_path, db_path)
        raise
    finally:
        conn.close()


def get_tweet_by_id(conn: sqlite3.Connection, tweet_id: str) -> sqlite3.Row | None:
    """Get a single tweet by ID."""
    cursor = conn.execute("SELECT * FROM tweets WHERE id = ?", (tweet_id,))
    return cursor.fetchone()
