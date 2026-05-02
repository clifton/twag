"""Schema Evolution Advisor.

Analyzes drift between the declarative ``SCHEMA`` in :mod:`twag.db.schema`,
the imperative ``ALTER TABLE`` migrations in :mod:`twag.db.connection`, and a
live SQLite database. Read-only by design — never mutates anything.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .schema import SCHEMA

Severity = str  # one of: "info", "warning", "error"


@dataclass
class SchemaFinding:
    """A single observation about schema drift."""

    severity: Severity
    category: str
    message: str
    suggested_action: str = ""

    def label(self) -> str:
        return f"[{self.severity.upper()}] {self.category}"


@dataclass
class SchemaReport:
    """Aggregate result of running the schema advisor."""

    findings: list[SchemaFinding] = field(default_factory=list)

    def add(self, finding: SchemaFinding) -> None:
        self.findings.append(finding)

    def errors(self) -> list[SchemaFinding]:
        return [f for f in self.findings if f.severity == "error"]

    def warnings(self) -> list[SchemaFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.findings)

    def is_empty(self) -> bool:
        return not self.findings


@dataclass
class SchemaSnapshot:
    """Tables, columns, and indexes loaded from a SQLite source."""

    tables: dict[str, set[str]] = field(default_factory=dict)
    indexes: set[str] = field(default_factory=set)
    objects: dict[str, str] = field(default_factory=dict)  # name -> object type


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _snapshot_from_connection(conn: sqlite3.Connection) -> SchemaSnapshot:
    """Read tables/columns/indexes from an open SQLite connection."""
    snap = SchemaSnapshot()
    cursor = conn.execute(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'index', 'view', 'trigger') "
        "AND name NOT LIKE 'sqlite_%'",
    )
    for row in cursor.fetchall():
        name, obj_type = row[0], row[1]
        snap.objects[name] = obj_type
        if obj_type == "table":
            cols = conn.execute(f"PRAGMA table_info({name})").fetchall()
            snap.tables[name] = {c[1] for c in cols}
        elif obj_type == "index":
            snap.indexes.add(name)
    return snap


def parse_schema_sql(sql: str | None = None) -> SchemaSnapshot:
    """Parse a schema script by loading it into an in-memory SQLite DB.

    Avoids regex parsing — we rely on SQLite's own parser by executing the
    DDL into a throwaway in-memory database and then introspecting it.
    """
    script = sql if sql is not None else SCHEMA
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(script)
        return _snapshot_from_connection(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Migration source introspection
# ---------------------------------------------------------------------------


_ALTER_RE = re.compile(
    r"ALTER\s+TABLE\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*)\s+"
    r"ADD\s+COLUMN\s+(?P<column>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


@dataclass
class MigrationSummary:
    """Per-table ALTER TABLE migrations discovered in source."""

    altered_columns: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def total(self) -> int:
        return sum(len(v) for v in self.altered_columns.values())


def _connection_source_path() -> Path:
    return Path(__file__).resolve().parent / "connection.py"


def parse_migrations(source: str | None = None) -> MigrationSummary:
    """Extract ALTER TABLE ... ADD COLUMN statements from connection.py."""
    if source is None:
        source = _connection_source_path().read_text(encoding="utf-8")
    summary = MigrationSummary()
    for match in _ALTER_RE.finditer(source):
        table = match.group("table")
        column = match.group("column")
        summary.altered_columns[table].append(column)
    return summary


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze_migrations(
    schema_sql: str | None = None,
    migration_source: str | None = None,
) -> SchemaReport:
    """Compare migrations in ``connection.py`` against the declarative ``SCHEMA``.

    Reports columns added through migrations that are also present in the
    declarative ``CREATE TABLE`` (the migration is now a safety net for older
    DBs — useful, but worth flagging as informational), and columns added via
    migrations that are *missing* from the declarative schema (a real drift).
    """
    report = SchemaReport()
    declared = parse_schema_sql(schema_sql)
    migrations = parse_migrations(migration_source)

    for table, columns in migrations.altered_columns.items():
        declared_cols = declared.tables.get(table)
        if declared_cols is None:
            report.add(
                SchemaFinding(
                    severity="error",
                    category="migration_orphan",
                    message=(f"Migration adds column(s) to '{table}' but no CREATE TABLE is declared in SCHEMA."),
                    suggested_action=f"Add CREATE TABLE {table} to twag/db/schema.py.",
                ),
            )
            continue

        seen: set[str] = set()
        for column in columns:
            if column in seen:
                report.add(
                    SchemaFinding(
                        severity="warning",
                        category="migration_duplicate",
                        message=f"Migration adds '{table}.{column}' more than once.",
                        suggested_action="Remove the duplicate ALTER TABLE block.",
                    ),
                )
                continue
            seen.add(column)
            if column not in declared_cols:
                report.add(
                    SchemaFinding(
                        severity="error",
                        category="migration_drift",
                        message=(
                            f"Migration adds '{table}.{column}' but the column is missing from CREATE TABLE in SCHEMA."
                        ),
                        suggested_action=(
                            f"Add '{column}' to the CREATE TABLE for '{table}' in "
                            f"twag/db/schema.py so fresh installs match migrated DBs."
                        ),
                    ),
                )
            else:
                report.add(
                    SchemaFinding(
                        severity="info",
                        category="migration_redundant",
                        message=(
                            f"Migration ALTER for '{table}.{column}' is also declared "
                            f"in CREATE TABLE — kept as a safety net for older DBs."
                        ),
                        suggested_action=("Once all live databases have run migrations, this branch can be retired."),
                    ),
                )

    return report


def analyze_database(
    db_path: Path,
    schema_sql: str | None = None,
) -> SchemaReport:
    """Compare a live SQLite DB at ``db_path`` against the declarative ``SCHEMA``.

    The database is opened readonly. We never write or migrate.
    """
    report = SchemaReport()
    if not db_path.exists():
        report.add(
            SchemaFinding(
                severity="error",
                category="database_missing",
                message=f"Database not found at {db_path}.",
                suggested_action="Run `twag db init` to create the database.",
            ),
        )
        return report

    declared = parse_schema_sql(schema_sql)

    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    try:
        live = _snapshot_from_connection(conn)
    finally:
        conn.close()

    # Tables declared but missing live
    for table, declared_cols in declared.tables.items():
        live_cols = live.tables.get(table)
        if live_cols is None:
            report.add(
                SchemaFinding(
                    severity="error",
                    category="table_missing",
                    message=f"Table '{table}' is declared in SCHEMA but missing from the database.",
                    suggested_action="Run `twag db init` (idempotent) to create missing tables.",
                ),
            )
            continue

        for column in sorted(declared_cols - live_cols):
            report.add(
                SchemaFinding(
                    severity="warning",
                    category="column_missing",
                    message=f"Column '{table}.{column}' is declared in SCHEMA but missing from the database.",
                    suggested_action="Run `twag db init` to apply pending migrations.",
                ),
            )

        for column in sorted(live_cols - declared_cols):
            report.add(
                SchemaFinding(
                    severity="info",
                    category="column_undeclared",
                    message=(f"Column '{table}.{column}' exists in the database but is not declared in SCHEMA."),
                    suggested_action=("Either add it to twag/db/schema.py or drop it (manual ALTER required)."),
                ),
            )

    # Tables in DB but not declared
    for table in sorted(set(live.tables) - set(declared.tables)):
        # Skip SQLite/FTS shadow tables
        if table.startswith("tweets_fts"):
            continue
        report.add(
            SchemaFinding(
                severity="info",
                category="table_undeclared",
                message=f"Table '{table}' exists in the database but is not declared in SCHEMA.",
                suggested_action="Either add it to twag/db/schema.py or drop it manually.",
            ),
        )

    # Indexes declared but missing live
    for index in sorted(declared.indexes - live.indexes):
        report.add(
            SchemaFinding(
                severity="warning",
                category="index_missing",
                message=f"Index '{index}' is declared in SCHEMA but missing from the database.",
                suggested_action="Run `twag db init` to create missing indexes.",
            ),
        )

    # Indexes in DB but not declared (skip SQLite-managed names)
    for index in sorted(live.indexes - declared.indexes):
        if index.startswith("sqlite_autoindex_"):
            continue
        report.add(
            SchemaFinding(
                severity="info",
                category="index_undeclared",
                message=f"Index '{index}' exists in the database but is not declared in SCHEMA.",
                suggested_action="Either add it to twag/db/schema.py or drop it manually.",
            ),
        )

    return report


def analyze_all(db_path: Path | None = None) -> SchemaReport:
    """Run both database and migration analyses, returning a merged report."""
    combined = SchemaReport()
    if db_path is not None:
        for finding in analyze_database(db_path).findings:
            combined.add(finding)
    for finding in analyze_migrations().findings:
        combined.add(finding)
    return combined
