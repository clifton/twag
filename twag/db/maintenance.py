"""Database maintenance operations: dump, restore, prune."""

import re
import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from ..config import get_database_path
from .connection import rebuild_fts

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
