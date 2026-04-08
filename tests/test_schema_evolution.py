"""Tests for the versioned schema migration framework."""

import sqlite3

import pytest

from twag.db.connection import get_connection, init_db
from twag.db.migrations import (
    TARGET_VERSION,
    check_schema,
    get_schema_version,
    run_migrations,
    set_schema_version,
)
from twag.db.schema import SCHEMA


@pytest.fixture
def fresh_db(tmp_path):
    """Create a fully initialized database via init_db."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with get_connection(db_path) as conn:
        yield conn


@pytest.fixture
def bare_db(tmp_path):
    """Create a database with only the base SCHEMA applied (version 0)."""
    db_path = tmp_path / "bare.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    yield conn
    conn.close()


class TestFreshInit:
    """Tests for a freshly initialized database."""

    def test_sets_target_version(self, fresh_db):
        version = get_schema_version(fresh_db)
        assert version == TARGET_VERSION

    def test_target_version_is_positive(self):
        assert TARGET_VERSION >= 1

    def test_all_expected_tables_exist(self, fresh_db):
        cursor = fresh_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = {row[0] for row in cursor.fetchall()}
        expected = {
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
        assert expected.issubset(tables)

    def test_schema_check_passes(self, fresh_db):
        result = check_schema(fresh_db)
        assert result["ok"] is True
        assert result["version_ok"] is True
        assert result["missing_tables"] == []
        assert result["missing_columns"] == {}


class TestMigrationFromZero:
    """Tests for migrating from version 0 to latest."""

    def test_bare_db_starts_at_version_zero(self, bare_db):
        assert get_schema_version(bare_db) == 0

    def test_migration_reaches_target(self, bare_db):
        new_version = run_migrations(bare_db)
        assert new_version == TARGET_VERSION

    def test_migration_adds_alert_log(self, bare_db):
        # alert_log is already in SCHEMA, but migration should still succeed
        run_migrations(bare_db)
        cursor = bare_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alert_log'")
        assert cursor.fetchone() is not None

    def test_migration_adds_metrics(self, bare_db):
        run_migrations(bare_db)
        cursor = bare_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metrics'")
        assert cursor.fetchone() is not None

    def test_migration_creates_indexes(self, bare_db):
        run_migrations(bare_db)
        cursor = bare_db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tweets_reply'")
        assert cursor.fetchone() is not None


class TestIdempotency:
    """Running migrations multiple times should be safe."""

    def test_double_run_same_version(self, bare_db):
        run_migrations(bare_db)
        v1 = get_schema_version(bare_db)
        # Run again
        run_migrations(bare_db)
        v2 = get_schema_version(bare_db)
        assert v1 == v2 == TARGET_VERSION

    def test_idempotent_on_fresh_db(self, fresh_db):
        """init_db already ran migrations; running again should be a no-op."""
        v_before = get_schema_version(fresh_db)
        run_migrations(fresh_db)
        v_after = get_schema_version(fresh_db)
        assert v_before == v_after == TARGET_VERSION


class TestSchemaCheck:
    """Tests for the schema drift detection."""

    def test_clean_db_no_drift(self, fresh_db):
        result = check_schema(fresh_db)
        assert result["ok"] is True

    def test_detects_version_mismatch(self, fresh_db):
        set_schema_version(fresh_db, 0)
        result = check_schema(fresh_db)
        assert result["version_ok"] is False
        assert result["ok"] is False

    def test_detects_missing_table(self, fresh_db):
        fresh_db.execute("DROP TABLE IF EXISTS metrics")
        result = check_schema(fresh_db)
        assert "metrics" in result["missing_tables"]
        assert result["ok"] is False

    def test_detects_missing_column(self, tmp_path):
        """Create a DB with a stripped-down tweets table to detect missing columns."""
        db_path = tmp_path / "stripped.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        # Minimal tweets table missing many columns
        conn.execute("CREATE TABLE tweets (id TEXT PRIMARY KEY, author_handle TEXT, content TEXT)")
        # Create other required tables so only column drift is detected
        conn.executescript("""
            CREATE TABLE accounts (handle TEXT PRIMARY KEY);
            CREATE TABLE narratives (id INTEGER PRIMARY KEY);
            CREATE TABLE tweet_narratives (tweet_id TEXT, narrative_id INTEGER);
            CREATE TABLE fetch_log (id INTEGER PRIMARY KEY);
            CREATE TABLE reactions (id INTEGER PRIMARY KEY);
            CREATE TABLE prompts (id INTEGER PRIMARY KEY);
            CREATE TABLE prompt_history (id INTEGER PRIMARY KEY);
            CREATE TABLE context_commands (id INTEGER PRIMARY KEY);
            CREATE TABLE alert_log (id INTEGER PRIMARY KEY);
            CREATE TABLE metrics (name TEXT);
        """)
        set_schema_version(conn, TARGET_VERSION)
        conn.commit()

        result = check_schema(conn)
        assert result["version_ok"] is True
        assert "tweets" in result["missing_columns"]
        assert "created_at" in result["missing_columns"]["tweets"]
        assert result["ok"] is False
        conn.close()


class TestVersionHelpers:
    """Tests for get/set schema version."""

    def test_roundtrip(self, bare_db):
        set_schema_version(bare_db, 42)
        assert get_schema_version(bare_db) == 42

    def test_default_is_zero(self, bare_db):
        assert get_schema_version(bare_db) == 0
