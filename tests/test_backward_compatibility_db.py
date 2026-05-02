"""Backward-compatibility guards for the SQLite schema.

Pins the contract that ``init_db`` must be able to upgrade an older database
in place — adding any new columns/tables/indexes without losing existing
rows. If a column is added to ``schema.py`` but not to the migration block in
``connection.py``, opening a legacy DB would raise ``OperationalError`` on
read paths; these tests catch that gap.
"""

import sqlite3

from twag.db import get_connection, init_db
from twag.db.schema import SCHEMA

# Minimum legacy column sets — what an older DB might contain. Every column
# added beyond this set must have an ``ALTER TABLE ... ADD COLUMN`` rule in
# ``_run_migrations`` so opening an old DB doesn't fail.
_LEGACY_TWEETS_COLUMNS = {
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
    "signal_tier",
    "tickers",
    "has_quote",
    "quote_tweet_id",
    "has_media",
    "media_analysis",
    "has_link",
    "link_summary",
    "included_in_digest",
}

_LEGACY_ACCOUNTS_COLUMNS = {
    "handle",
    "display_name",
    "tier",
    "weight",
    "category",
    "tweets_seen",
    "tweets_kept",
    "avg_relevance_score",
    "last_high_signal_at",
    "added_at",
    "auto_promoted",
    "muted",
}

# Tables that newer code expects to find. If a table is added to schema.py
# without a ``CREATE TABLE IF NOT EXISTS`` reachable from ``init_db``, this
# test breaks before users hit a runtime error.
_REQUIRED_TABLES = {
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
    "llm_usage",
    "media_analysis_cache",
    "tweets_fts",
}

_REQUIRED_INDEXES = {
    "idx_tweets_processed_score",
    "idx_tweets_author",
    "idx_tweets_signal_tier",
    "idx_tweets_bookmarked",
    "idx_tweets_quote",
    "idx_fetch_log_endpoint",
    "idx_reactions_tweet",
    "idx_prompt_history_name",
    "idx_alert_log_sent",
    "idx_metrics_name",
    "idx_llm_usage_called_at",
    "idx_media_analysis_cache_updated",
}


def _create_legacy_db(db_path) -> None:
    """Create a synthetic legacy DB with only the original columns."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE tweets (
            id TEXT PRIMARY KEY,
            author_handle TEXT NOT NULL,
            author_name TEXT,
            content TEXT NOT NULL,
            created_at TIMESTAMP,
            first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT,
            processed_at TIMESTAMP,
            relevance_score REAL,
            category TEXT,
            summary TEXT,
            signal_tier TEXT,
            tickers TEXT,
            has_quote INTEGER DEFAULT 0,
            quote_tweet_id TEXT,
            has_media INTEGER DEFAULT 0,
            media_analysis TEXT,
            has_link INTEGER DEFAULT 0,
            link_summary TEXT,
            included_in_digest TEXT
        );
        CREATE TABLE accounts (
            handle TEXT PRIMARY KEY,
            display_name TEXT,
            tier INTEGER DEFAULT 2,
            weight REAL DEFAULT 50.0,
            category TEXT,
            tweets_seen INTEGER DEFAULT 0,
            tweets_kept INTEGER DEFAULT 0,
            avg_relevance_score REAL,
            last_high_signal_at TIMESTAMP,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            auto_promoted INTEGER DEFAULT 0,
            muted INTEGER DEFAULT 0
        );
        """,
    )
    conn.execute(
        "INSERT INTO tweets (id, author_handle, content, summary, signal_tier, tickers, has_quote) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("legacy-1", "alice", "Fed pivot incoming", "fed pivot", "high_signal", "TLT,GLD", 0),
    )
    conn.execute(
        "INSERT INTO tweets (id, author_handle, content, summary, signal_tier, tickers, has_quote) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("legacy-2", "bob", "AAPL earnings beat", "aapl beat", "market_relevant", "AAPL", 0),
    )
    conn.execute(
        "INSERT INTO accounts (handle, tier, weight) VALUES (?, ?, ?)",
        ("alice", 1, 80.0),
    )
    conn.commit()
    conn.close()


def _current_tweet_columns() -> set[str]:
    """Parse ``schema.py`` SCHEMA to extract the current tweets column set."""
    # Use a temp in-memory DB to ask SQLite what columns the current SCHEMA defines.
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tweets)").fetchall()}
    conn.close()
    return cols


def _current_account_columns() -> set[str]:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()}
    conn.close()
    return cols


def test_legacy_db_gets_all_current_tweet_columns(tmp_path):
    """Every column in the current schema must exist after init_db on a legacy DB."""
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    init_db(db_path)

    with get_connection(db_path, readonly=True) as conn:
        actual = {row[1] for row in conn.execute("PRAGMA table_info(tweets)").fetchall()}

    expected = _current_tweet_columns()
    missing = expected - actual
    assert not missing, (
        f"init_db failed to add these tweets columns to a legacy DB: {missing}. "
        "Add an ALTER TABLE rule in twag/db/connection.py:_run_migrations."
    )


def test_legacy_db_gets_all_current_account_columns(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    init_db(db_path)

    with get_connection(db_path, readonly=True) as conn:
        actual = {row[1] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()}

    expected = _current_account_columns()
    missing = expected - actual
    assert not missing, f"init_db failed to add accounts columns: {missing}"


def test_legacy_db_gets_all_required_tables(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    init_db(db_path)

    with get_connection(db_path, readonly=True) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual')").fetchall()
        }
        # FTS5 reports as a regular table in sqlite_master.

    missing = _REQUIRED_TABLES - tables
    assert not missing, f"init_db failed to create tables on legacy DB: {missing}"


def test_legacy_db_gets_required_indexes(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    init_db(db_path)

    with get_connection(db_path, readonly=True) as conn:
        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}

    missing = _REQUIRED_INDEXES - indexes
    assert not missing, f"init_db failed to create required indexes: {missing}"


def test_legacy_rows_survive_migration(tmp_path):
    """Existing rows must remain intact and queryable after init_db."""
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    init_db(db_path)

    with get_connection(db_path, readonly=True) as conn:
        rows = list(conn.execute("SELECT id, author_handle, content FROM tweets ORDER BY id"))
        assert len(rows) == 2
        assert rows[0]["id"] == "legacy-1"
        assert rows[0]["author_handle"] == "alice"
        assert "Fed pivot" in rows[0]["content"]
        assert rows[1]["id"] == "legacy-2"

        accts = list(conn.execute("SELECT handle, tier, weight FROM accounts"))
        assert len(accts) == 1
        assert accts[0]["handle"] == "alice"
        assert accts[0]["tier"] == 1


def test_legacy_db_fts_is_populated(tmp_path):
    """FTS index must be backfilled from existing rows during init_db."""
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    init_db(db_path)

    with get_connection(db_path, readonly=True) as conn:
        result = conn.execute("SELECT rowid FROM tweets_fts WHERE tweets_fts MATCH 'Fed'").fetchall()
        assert len(result) >= 1, "FTS index was not populated from existing tweets"

        result = conn.execute("SELECT rowid FROM tweets_fts WHERE tweets_fts MATCH 'AAPL'").fetchall()
        assert len(result) >= 1


def test_legacy_columns_subset_of_current(tmp_path):
    """Sanity check that our legacy column set is actually a subset of current.

    Guards against accidental drift: if someone removes a 'legacy' column from
    schema.py the test for migration completeness becomes meaningless.
    """
    current_tweets = _current_tweet_columns()
    current_accounts = _current_account_columns()

    drifted = _LEGACY_TWEETS_COLUMNS - current_tweets
    assert not drifted, f"Legacy tweet columns no longer in current schema: {drifted}"

    drifted = _LEGACY_ACCOUNTS_COLUMNS - current_accounts
    assert not drifted, f"Legacy account columns no longer in current schema: {drifted}"


def test_init_db_is_idempotent(tmp_path):
    """Running init_db twice on a legacy DB must not error or duplicate rows."""
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)

    init_db(db_path)
    init_db(db_path)

    with get_connection(db_path, readonly=True) as conn:
        count = conn.execute("SELECT COUNT(*) FROM tweets").fetchone()[0]
        assert count == 2
