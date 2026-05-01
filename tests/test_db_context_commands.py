"""Tests for twag.db.context_commands — context command CRUD."""

import sqlite3

import pytest

from twag.db.context_commands import (
    ContextCommand,
    delete_context_command,
    get_all_context_commands,
    get_context_command,
    toggle_context_command,
    upsert_context_command,
)


@pytest.fixture
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE context_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            command_template TEXT NOT NULL,
            description TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    return conn


class TestUpsert:
    def test_insert_returns_id(self, conn: sqlite3.Connection) -> None:
        cid = upsert_context_command(conn, "snapshot", "echo {tweet_date}", description="Daily snapshot")
        assert cid > 0

    def test_update_overrides_template(self, conn: sqlite3.Connection) -> None:
        upsert_context_command(conn, "snapshot", "echo v1", description="Original")
        upsert_context_command(conn, "snapshot", "echo v2")
        cmd = get_context_command(conn, "snapshot")
        assert cmd is not None
        assert cmd.command_template == "echo v2"
        # COALESCE preserves description when the new value is None.
        assert cmd.description == "Original"

    def test_disabled_flag_round_trips(self, conn: sqlite3.Connection) -> None:
        upsert_context_command(conn, "x", "true", enabled=False)
        cmd = get_context_command(conn, "x")
        assert cmd is not None
        assert cmd.enabled is False


class TestGetContextCommand:
    def test_unknown_returns_none(self, conn: sqlite3.Connection) -> None:
        assert get_context_command(conn, "missing") is None

    def test_enabled_field_is_bool(self, conn: sqlite3.Connection) -> None:
        upsert_context_command(conn, "x", "true")
        cmd = get_context_command(conn, "x")
        assert isinstance(cmd, ContextCommand)
        assert cmd.enabled is True

    def test_unparseable_timestamp_falls_back_to_none(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO context_commands (name, command_template, created_at) VALUES (?, ?, ?)",
            ("bad", "true", "not-a-date"),
        )
        cmd = get_context_command(conn, "bad")
        assert cmd is not None
        assert cmd.created_at is None


class TestGetAll:
    def test_returns_all_alphabetical(self, conn: sqlite3.Connection) -> None:
        upsert_context_command(conn, "z_cmd", "true")
        upsert_context_command(conn, "a_cmd", "true")
        rows = get_all_context_commands(conn)
        names = [c.name for c in rows]
        assert names == sorted(names)

    def test_enabled_only_filters(self, conn: sqlite3.Connection) -> None:
        upsert_context_command(conn, "on", "true", enabled=True)
        upsert_context_command(conn, "off", "true", enabled=False)
        rows = get_all_context_commands(conn, enabled_only=True)
        assert {c.name for c in rows} == {"on"}


class TestDelete:
    def test_delete_existing(self, conn: sqlite3.Connection) -> None:
        upsert_context_command(conn, "x", "true")
        assert delete_context_command(conn, "x") is True
        assert get_context_command(conn, "x") is None

    def test_delete_missing_returns_false(self, conn: sqlite3.Connection) -> None:
        assert delete_context_command(conn, "missing") is False


class TestToggle:
    def test_toggle_existing(self, conn: sqlite3.Connection) -> None:
        upsert_context_command(conn, "x", "true", enabled=True)
        assert toggle_context_command(conn, "x", enabled=False) is True
        cmd = get_context_command(conn, "x")
        assert cmd is not None
        assert cmd.enabled is False

    def test_toggle_missing_returns_false(self, conn: sqlite3.Connection) -> None:
        assert toggle_context_command(conn, "missing", enabled=True) is False
