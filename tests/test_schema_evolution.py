"""Tests for the versioned schema migration framework."""

import sqlite3

from twag.db.connection import init_db
from twag.db.migrations import (
    LATEST_VERSION,
    MIGRATIONS,
    _get_columns,
    ensure_schema_migrations_table,
    get_applied_migrations,
    get_current_version,
    get_expected_tables,
    get_pending_migrations,
    run_pending_migrations,
)
from twag.db.schema import SCHEMA


def _fresh_conn() -> sqlite3.Connection:
    """In-memory database with full schema applied (simulates init_db)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _bare_conn() -> sqlite3.Connection:
    """In-memory database with only the oldest baseline tables (pre-migration)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Minimal v0 schema: tweets without any migration columns, accounts without last_fetched_at
    conn.executescript("""
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
        CREATE TABLE narratives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_mentioned_at TIMESTAMP,
            mention_count INTEGER DEFAULT 1,
            sentiment TEXT,
            related_tickers TEXT,
            active INTEGER DEFAULT 1
        );
        CREATE TABLE tweet_narratives (
            tweet_id TEXT,
            narrative_id INTEGER,
            PRIMARY KEY (tweet_id, narrative_id)
        );
        CREATE TABLE fetch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT NOT NULL,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tweets_fetched INTEGER,
            new_tweets INTEGER,
            query_params TEXT
        );
        CREATE TABLE reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tweet_id TEXT NOT NULL,
            reaction_type TEXT NOT NULL,
            reason TEXT,
            target TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            template TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT
        );
        CREATE TABLE prompt_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_name TEXT NOT NULL,
            template TEXT NOT NULL,
            version INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE context_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            command_template TEXT NOT NULL,
            description TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    return conn


class TestFreshDatabase:
    """Fresh DB should get latest version after running all migrations."""

    def test_fresh_db_gets_latest_version(self):
        conn = _fresh_conn()
        applied = run_pending_migrations(conn)
        version = get_current_version(conn)
        assert version == LATEST_VERSION
        assert len(applied) == len(MIGRATIONS)

    def test_fresh_db_records_all_migrations(self):
        conn = _fresh_conn()
        run_pending_migrations(conn)
        recorded = get_applied_migrations(conn)
        assert len(recorded) == len(MIGRATIONS)
        versions = [r["version"] for r in recorded]
        assert versions == list(range(1, LATEST_VERSION + 1))


class TestOldDatabaseUpgrade:
    """Old DB with missing columns should upgrade correctly."""

    def test_old_db_adds_bookmark_columns(self):
        conn = _bare_conn()
        cols_before = _get_columns(conn, "tweets")
        assert "bookmarked" not in cols_before

        run_pending_migrations(conn)

        cols_after = _get_columns(conn, "tweets")
        assert "bookmarked" in cols_after
        assert "bookmarked_at" in cols_after

    def test_old_db_adds_retweet_columns(self):
        conn = _bare_conn()
        run_pending_migrations(conn)
        cols = _get_columns(conn, "tweets")
        assert "is_retweet" in cols
        assert "retweeted_by_handle" in cols
        assert "original_tweet_id" in cols

    def test_old_db_adds_article_columns(self):
        conn = _bare_conn()
        run_pending_migrations(conn)
        cols = _get_columns(conn, "tweets")
        assert "is_x_article" in cols
        assert "article_summary_short" in cols
        assert "article_top_visual_json" in cols

    def test_old_db_adds_links_columns(self):
        conn = _bare_conn()
        run_pending_migrations(conn)
        cols = _get_columns(conn, "tweets")
        assert "links_json" in cols
        assert "in_reply_to_tweet_id" in cols
        assert "links_expanded_at" in cols

    def test_old_db_creates_alert_log(self):
        conn = _bare_conn()
        run_pending_migrations(conn)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alert_log'")
        assert cursor.fetchone() is not None

    def test_old_db_creates_metrics(self):
        conn = _bare_conn()
        run_pending_migrations(conn)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metrics'")
        assert cursor.fetchone() is not None

    def test_old_db_adds_accounts_last_fetched(self):
        conn = _bare_conn()
        cols_before = _get_columns(conn, "accounts")
        assert "last_fetched_at" not in cols_before

        run_pending_migrations(conn)
        cols_after = _get_columns(conn, "accounts")
        assert "last_fetched_at" in cols_after

    def test_old_db_reaches_latest_version(self):
        conn = _bare_conn()
        run_pending_migrations(conn)
        assert get_current_version(conn) == LATEST_VERSION


class TestIdempotency:
    """Migrations must be idempotent — running twice should be safe."""

    def test_run_twice_no_error(self):
        conn = _fresh_conn()
        run_pending_migrations(conn)
        # Run again — should be a no-op
        applied = run_pending_migrations(conn)
        assert applied == []

    def test_run_on_bare_twice_no_error(self):
        conn = _bare_conn()
        run_pending_migrations(conn)
        applied = run_pending_migrations(conn)
        assert applied == []
        assert get_current_version(conn) == LATEST_VERSION


class TestSchemaStatus:
    """Schema-status should report correct state."""

    def test_pending_on_bare(self):
        conn = _bare_conn()
        ensure_schema_migrations_table(conn)
        current = get_current_version(conn)
        assert current == 0
        pending = get_pending_migrations(current)
        assert len(pending) == len(MIGRATIONS)

    def test_no_pending_after_migrations(self):
        conn = _fresh_conn()
        run_pending_migrations(conn)
        current = get_current_version(conn)
        pending = get_pending_migrations(current)
        assert pending == []

    def test_expected_tables_match_schema(self):
        conn = _fresh_conn()
        run_pending_migrations(conn)
        expected = get_expected_tables()
        for table, expected_cols in expected.items():
            actual_cols = _get_columns(conn, table)
            missing = expected_cols - actual_cols
            assert not missing, f"{table} missing columns: {missing}"


class TestDryRun:
    """Dry-run should produce no side effects."""

    def test_dry_run_no_version_change(self):
        conn = _bare_conn()
        ensure_schema_migrations_table(conn)
        version_before = get_current_version(conn)
        pending = run_pending_migrations(conn, dry_run=True)
        version_after = get_current_version(conn)
        assert version_before == version_after
        assert len(pending) == len(MIGRATIONS)

    def test_dry_run_no_audit_records(self):
        conn = _bare_conn()
        ensure_schema_migrations_table(conn)
        run_pending_migrations(conn, dry_run=True)
        recorded = get_applied_migrations(conn)
        assert recorded == []

    def test_dry_run_no_column_changes(self):
        conn = _bare_conn()
        cols_before = _get_columns(conn, "tweets")
        ensure_schema_migrations_table(conn)
        run_pending_migrations(conn, dry_run=True)
        cols_after = _get_columns(conn, "tweets")
        assert cols_before == cols_after


class TestInitDb:
    """init_db should work end-to-end with the new migration system."""

    def test_init_db_sets_version(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        version = get_current_version(conn)
        assert version == LATEST_VERSION
        conn.close()

    def test_init_db_idempotent(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        init_db(db_path)  # Should not raise
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        assert get_current_version(conn) == LATEST_VERSION
        conn.close()
