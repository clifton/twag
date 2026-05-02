"""Tests for twag.db.schema_advisor."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from twag.db.schema_advisor import (
    analyze_database,
    analyze_migrations,
    parse_migrations,
    parse_schema_sql,
)

if TYPE_CHECKING:
    from pathlib import Path

SIMPLE_SCHEMA = """
CREATE TABLE tweets (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    bookmarked INTEGER DEFAULT 0
);
CREATE INDEX idx_tweets_content ON tweets(content);
"""


def _build_db(path: Path, schema_sql: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


def test_parse_schema_sql_extracts_tables_and_indexes() -> None:
    snap = parse_schema_sql(SIMPLE_SCHEMA)

    assert "tweets" in snap.tables
    assert snap.tables["tweets"] == {"id", "content", "bookmarked"}
    assert "idx_tweets_content" in snap.indexes


def test_clean_db_matching_schema_has_no_findings(tmp_path: Path) -> None:
    db_path = tmp_path / "clean.db"
    _build_db(db_path, SIMPLE_SCHEMA)

    report = analyze_database(db_path, schema_sql=SIMPLE_SCHEMA)

    assert report.is_empty(), [f.message for f in report.findings]
    assert not report.has_errors()


def test_db_missing_migrated_column_warns(tmp_path: Path) -> None:
    db_path = tmp_path / "stale.db"
    # Live DB lacks 'bookmarked' which the schema declares
    _build_db(
        db_path,
        """
        CREATE TABLE tweets (id TEXT PRIMARY KEY, content TEXT NOT NULL);
        CREATE INDEX idx_tweets_content ON tweets(content);
        """,
    )

    report = analyze_database(db_path, schema_sql=SIMPLE_SCHEMA)

    findings = [f for f in report.findings if f.category == "column_missing"]
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert "bookmarked" in findings[0].message


def test_db_with_extra_column_is_info(tmp_path: Path) -> None:
    db_path = tmp_path / "extra.db"
    _build_db(
        db_path,
        """
        CREATE TABLE tweets (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            bookmarked INTEGER DEFAULT 0,
            ghost_field TEXT
        );
        CREATE INDEX idx_tweets_content ON tweets(content);
        """,
    )

    report = analyze_database(db_path, schema_sql=SIMPLE_SCHEMA)

    findings = [f for f in report.findings if f.category == "column_undeclared"]
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert "ghost_field" in findings[0].message
    assert not report.has_errors()


def test_missing_index_is_warning(tmp_path: Path) -> None:
    db_path = tmp_path / "noindex.db"
    _build_db(
        db_path,
        """
        CREATE TABLE tweets (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            bookmarked INTEGER DEFAULT 0
        );
        """,
    )

    report = analyze_database(db_path, schema_sql=SIMPLE_SCHEMA)

    findings = [f for f in report.findings if f.category == "index_missing"]
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert "idx_tweets_content" in findings[0].message


def test_undeclared_table_is_info(tmp_path: Path) -> None:
    db_path = tmp_path / "extratable.db"
    _build_db(
        db_path,
        """
        CREATE TABLE tweets (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            bookmarked INTEGER DEFAULT 0
        );
        CREATE INDEX idx_tweets_content ON tweets(content);
        CREATE TABLE legacy (id INTEGER PRIMARY KEY);
        """,
    )

    report = analyze_database(db_path, schema_sql=SIMPLE_SCHEMA)

    findings = [f for f in report.findings if f.category == "table_undeclared"]
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert "legacy" in findings[0].message


def test_missing_database_returns_error(tmp_path: Path) -> None:
    db_path = tmp_path / "does-not-exist.db"

    report = analyze_database(db_path, schema_sql=SIMPLE_SCHEMA)

    assert report.has_errors()
    assert report.findings[0].category == "database_missing"


def test_parse_migrations_extracts_alter_table_columns() -> None:
    source = """
    def _run_migrations(conn):
        if "foo" not in cols:
            conn.execute("ALTER TABLE tweets ADD COLUMN foo TEXT")
        if "bar" not in cols:
            conn.execute("ALTER TABLE tweets ADD COLUMN bar INTEGER DEFAULT 0")
        if "baz" not in cols:
            conn.execute("ALTER TABLE accounts ADD COLUMN baz TIMESTAMP")
    """

    summary = parse_migrations(source)

    assert summary.altered_columns["tweets"] == ["foo", "bar"]
    assert summary.altered_columns["accounts"] == ["baz"]
    assert summary.total() == 3


def test_redundant_migration_detected() -> None:
    schema = """
    CREATE TABLE tweets (id TEXT PRIMARY KEY, foo TEXT, bar INTEGER);
    """
    migration_source = """
    conn.execute("ALTER TABLE tweets ADD COLUMN foo TEXT")
    conn.execute("ALTER TABLE tweets ADD COLUMN bar INTEGER DEFAULT 0")
    """

    report = analyze_migrations(schema_sql=schema, migration_source=migration_source)

    redundants = [f for f in report.findings if f.category == "migration_redundant"]
    assert len(redundants) == 2
    assert all(f.severity == "info" for f in redundants)
    assert not report.has_errors()


def test_migration_drift_detected_when_column_not_in_schema() -> None:
    schema = """
    CREATE TABLE tweets (id TEXT PRIMARY KEY, foo TEXT);
    """
    migration_source = """
    conn.execute("ALTER TABLE tweets ADD COLUMN foo TEXT")
    conn.execute("ALTER TABLE tweets ADD COLUMN missing TEXT")
    """

    report = analyze_migrations(schema_sql=schema, migration_source=migration_source)

    drifts = [f for f in report.findings if f.category == "migration_drift"]
    assert len(drifts) == 1
    assert drifts[0].severity == "error"
    assert "missing" in drifts[0].message
    assert report.has_errors()


def test_migration_orphan_when_table_missing_in_schema() -> None:
    schema = "CREATE TABLE other (id TEXT);"
    migration_source = 'conn.execute("ALTER TABLE tweets ADD COLUMN foo TEXT")'

    report = analyze_migrations(schema_sql=schema, migration_source=migration_source)

    orphans = [f for f in report.findings if f.category == "migration_orphan"]
    assert len(orphans) == 1
    assert orphans[0].severity == "error"


def test_real_schema_and_migrations_have_no_drift_errors() -> None:
    """The shipped SCHEMA + connection.py migrations should be consistent."""
    report = analyze_migrations()

    drift = [f for f in report.findings if f.category == "migration_drift"]
    orphans = [f for f in report.findings if f.category == "migration_orphan"]
    duplicates = [f for f in report.findings if f.category == "migration_duplicate"]

    assert drift == [], [f.message for f in drift]
    assert orphans == [], [f.message for f in orphans]
    assert duplicates == [], [f.message for f in duplicates]
