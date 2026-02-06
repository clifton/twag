"""Context command CRUD operations for CLI-based context enrichment."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime


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
