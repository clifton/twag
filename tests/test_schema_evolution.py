"""Tests for schema version tracking and get_schema_info()."""

import sqlite3

import pytest

from twag.db import get_connection, get_schema_info, init_db
from twag.db.schema import CURRENT_SCHEMA_VERSION


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


def test_fresh_db_schema_info(db_path):
    """A freshly initialised db should report no drift."""
    with get_connection(db_path) as conn:
        info = get_schema_info(conn)

    assert info["user_version"] == CURRENT_SCHEMA_VERSION
    assert info["expected_version"] == CURRENT_SCHEMA_VERSION
    assert info["version_match"] is True
    assert info["missing_columns"] == {}
    assert info["missing_indexes"] == []


def test_user_version_set_after_init(db_path):
    """PRAGMA user_version should equal CURRENT_SCHEMA_VERSION after init_db."""
    with get_connection(db_path) as conn:
        ver = conn.execute("PRAGMA user_version").fetchone()[0]
    assert ver == CURRENT_SCHEMA_VERSION


def test_missing_column_detected(db_path):
    """Dropping a column should show up in missing_columns."""
    # SQLite >=3.35 supports DROP COLUMN; simulate old schema by recreating
    # the accounts table without last_fetched_at.
    with get_connection(db_path) as conn:
        # Get current columns minus one
        cursor = conn.execute("PRAGMA table_info(accounts)")
        cols = [row[1] for row in cursor.fetchall() if row[1] != "last_fetched_at"]
        col_list = ", ".join(cols)

        conn.execute("ALTER TABLE accounts RENAME TO accounts_old")
        conn.execute(f"CREATE TABLE accounts AS SELECT {col_list} FROM accounts_old")
        conn.execute("DROP TABLE accounts_old")
        conn.commit()

        info = get_schema_info(conn)

    assert "accounts" in info["missing_columns"]
    assert "last_fetched_at" in info["missing_columns"]["accounts"]


def test_missing_index_detected(db_path):
    """Dropping an index should show up in missing_indexes."""
    with get_connection(db_path) as conn:
        conn.execute("DROP INDEX IF EXISTS idx_tweets_author")
        info = get_schema_info(conn)

    assert "idx_tweets_author" in info["missing_indexes"]


def test_version_drift_detected(tmp_path):
    """A db with user_version=0 (never set) should report drift."""
    path = tmp_path / "old.db"
    # Create a db without going through init_db (simulates legacy)
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE tweets (id TEXT PRIMARY KEY, author_handle TEXT NOT NULL, content TEXT NOT NULL)")
    conn.commit()
    conn.close()

    with get_connection(path) as conn:
        info = get_schema_info(conn)

    assert info["user_version"] == 0
    assert info["version_match"] is False
