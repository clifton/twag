"""Tests for schema evolution: versioning, migration registry, drift detection."""

import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from twag.db.connection import (
    MIGRATIONS,
    _run_migrations,
    _validate_schema,
    get_pending_migrations,
    get_schema_drift,
    get_schema_version,
)
from twag.db.schema import ACCOUNTS_COLUMNS, SCHEMA, SCHEMA_VERSION, TWEETS_COLUMNS


@pytest.fixture
def tmp_db(tmp_path: Path):
    """Create a fresh in-memory-style DB on disk with base schema."""
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    yield conn
    conn.close()


class TestVersionTracking:
    def test_fresh_db_starts_at_zero(self, tmp_db: sqlite3.Connection):
        assert get_schema_version(tmp_db) == 0

    def test_migrations_set_version(self, tmp_db: sqlite3.Connection):
        _run_migrations(tmp_db)
        assert get_schema_version(tmp_db) == SCHEMA_VERSION

    def test_version_matches_max_migration(self):
        max_migration_version = max(v for v, _, _ in MIGRATIONS)
        assert max_migration_version == SCHEMA_VERSION


class TestMigrationIdempotency:
    def test_run_twice_no_errors(self, tmp_db: sqlite3.Connection):
        _run_migrations(tmp_db)
        tmp_db.commit()
        # Run again — should be a no-op
        _run_migrations(tmp_db)
        tmp_db.commit()
        assert get_schema_version(tmp_db) == SCHEMA_VERSION

    def test_pending_empty_after_migration(self, tmp_db: sqlite3.Connection):
        _run_migrations(tmp_db)
        assert get_pending_migrations(tmp_db) == []

    def test_pending_before_migration(self, tmp_db: sqlite3.Connection):
        pending = get_pending_migrations(tmp_db)
        assert len(pending) == len(MIGRATIONS)


class TestDriftDetection:
    def test_no_drift_on_fresh_schema(self, tmp_db: sqlite3.Connection):
        _run_migrations(tmp_db)
        drift = get_schema_drift(tmp_db)
        assert drift == {}

    def test_missing_column_detected(self, tmp_db: sqlite3.Connection):
        _run_migrations(tmp_db)
        # Simulate drift by adding a column to the expected set
        # Instead, we'll drop a column by recreating without it — but SQLite
        # doesn't support DROP COLUMN in older versions.  Easier: temporarily
        # patch the constant.
        import twag.db.connection as mod

        original = mod.TWEETS_COLUMNS
        try:
            mod.TWEETS_COLUMNS = original | {"fake_future_col"}
            drift = get_schema_drift(tmp_db)
            assert "tweets" in drift
            assert "fake_future_col" in drift["tweets"]["missing"]
        finally:
            mod.TWEETS_COLUMNS = original

    def test_extra_column_detected(self, tmp_db: sqlite3.Connection):
        _run_migrations(tmp_db)
        tmp_db.execute("ALTER TABLE tweets ADD COLUMN rogue_col TEXT")
        drift = get_schema_drift(tmp_db)
        assert "tweets" in drift
        assert "rogue_col" in drift["tweets"]["extra"]

    def test_validate_schema_logs_drift(self, tmp_db: sqlite3.Connection, caplog):
        _run_migrations(tmp_db)
        tmp_db.execute("ALTER TABLE accounts ADD COLUMN rogue_col TEXT")
        import logging

        with caplog.at_level(logging.WARNING):
            _validate_schema(tmp_db)
        assert "rogue_col" in caplog.text

    def test_column_constants_match_schema(self, tmp_db: sqlite3.Connection):
        """Verify TWEETS_COLUMNS and ACCOUNTS_COLUMNS match the CREATE TABLE."""
        _run_migrations(tmp_db)
        cursor = tmp_db.execute("PRAGMA table_info(tweets)")
        actual_tweets = {row[1] for row in cursor.fetchall()}
        assert actual_tweets == TWEETS_COLUMNS

        cursor = tmp_db.execute("PRAGMA table_info(accounts)")
        actual_accounts = {row[1] for row in cursor.fetchall()}
        assert actual_accounts == ACCOUNTS_COLUMNS


class TestSchemaStatusCLI:
    def test_schema_status_output(self, tmp_path: Path, monkeypatch):
        from twag.cli.db_cmd import db_schema_status

        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(db_file)
        conn.executescript(SCHEMA)
        _run_migrations(conn)
        conn.commit()
        conn.close()

        monkeypatch.setattr("twag.cli.db_cmd.get_database_path", lambda: db_file)
        monkeypatch.setattr("twag.db.connection.get_database_path", lambda: db_file)

        runner = CliRunner()
        result = runner.invoke(db_schema_status)
        assert result.exit_code == 0
        assert f"Schema version: {SCHEMA_VERSION}" in result.output
        assert "All migrations applied" in result.output
        assert "No column drift" in result.output

    def test_schema_status_pending(self, tmp_path: Path, monkeypatch):
        from twag.cli.db_cmd import db_schema_status

        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(db_file)
        conn.executescript(SCHEMA)
        # Don't run migrations — version stays at 0
        conn.close()

        monkeypatch.setattr("twag.cli.db_cmd.get_database_path", lambda: db_file)
        monkeypatch.setattr("twag.db.connection.get_database_path", lambda: db_file)

        runner = CliRunner()
        result = runner.invoke(db_schema_status)
        assert result.exit_code == 0
        assert "pending migration" in result.output
