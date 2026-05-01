"""Tests for twag.db.prompts — editable prompt CRUD with versioning."""

import sqlite3

import pytest

from twag.db.prompts import (
    DEFAULT_PROMPTS,
    Prompt,
    get_all_prompts,
    get_prompt,
    get_prompt_history,
    rollback_prompt,
    seed_prompts,
    upsert_prompt,
)


@pytest.fixture
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
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
        """,
    )
    return conn


class TestSeedPrompts:
    def test_seeds_all_defaults_on_empty_db(self, conn: sqlite3.Connection) -> None:
        count = seed_prompts(conn)
        assert count == len(DEFAULT_PROMPTS)
        rows = conn.execute("SELECT name FROM prompts").fetchall()
        assert {r["name"] for r in rows} == set(DEFAULT_PROMPTS.keys())

    def test_seed_is_idempotent(self, conn: sqlite3.Connection) -> None:
        seed_prompts(conn)
        # Second invocation should insert nothing.
        assert seed_prompts(conn) == 0

    def test_seed_skips_existing_names(self, conn: sqlite3.Connection) -> None:
        # Pre-insert one prompt with a custom template.
        upsert_prompt(conn, "triage", "custom", updated_by="user")
        seed_prompts(conn)
        prompt = get_prompt(conn, "triage")
        assert prompt is not None
        assert prompt.template == "custom"


class TestGetPrompt:
    def test_returns_none_for_unknown(self, conn: sqlite3.Connection) -> None:
        assert get_prompt(conn, "nope") is None

    def test_returns_prompt_with_parsed_timestamp(self, conn: sqlite3.Connection) -> None:
        seed_prompts(conn)
        result = get_prompt(conn, "triage")
        assert isinstance(result, Prompt)
        assert result.name == "triage"
        assert result.version == 1
        assert result.updated_at is not None  # ISO timestamp parsed.
        assert result.updated_by == "seed"

    def test_handles_unparseable_timestamp(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO prompts (name, template, version, updated_at, updated_by) VALUES (?, ?, ?, ?, ?)",
            ("bad", "x", 1, "not-a-date", "test"),
        )
        result = get_prompt(conn, "bad")
        assert result is not None
        assert result.updated_at is None


class TestGetAllPrompts:
    def test_returns_alphabetical(self, conn: sqlite3.Connection) -> None:
        upsert_prompt(conn, "z_last", "tpl")
        upsert_prompt(conn, "a_first", "tpl")
        rows = get_all_prompts(conn)
        names = [p.name for p in rows]
        assert names == sorted(names)


class TestUpsertPrompt:
    def test_insert_starts_at_version_1(self, conn: sqlite3.Connection) -> None:
        version = upsert_prompt(conn, "new", "v1 template")
        assert version == 1
        result = get_prompt(conn, "new")
        assert result is not None
        assert result.template == "v1 template"
        # No history row for the very first insert.
        assert get_prompt_history(conn, "new") == []

    def test_update_increments_version_and_archives_old(self, conn: sqlite3.Connection) -> None:
        upsert_prompt(conn, "evolving", "v1")
        new_version = upsert_prompt(conn, "evolving", "v2", updated_by="user")
        assert new_version == 2

        result = get_prompt(conn, "evolving")
        assert result is not None
        assert result.template == "v2"
        assert result.version == 2

        history = get_prompt_history(conn, "evolving")
        assert len(history) == 1
        assert history[0]["template"] == "v1"
        assert history[0]["version"] == 1


class TestPromptHistory:
    def test_history_orders_newest_first_and_respects_limit(self, conn: sqlite3.Connection) -> None:
        upsert_prompt(conn, "name", "v1")
        upsert_prompt(conn, "name", "v2")
        upsert_prompt(conn, "name", "v3")
        history = get_prompt_history(conn, "name", limit=2)
        assert len(history) == 2
        assert history[0]["version"] == 2
        assert history[1]["version"] == 1


class TestRollbackPrompt:
    def test_rollback_to_existing_version_succeeds(self, conn: sqlite3.Connection) -> None:
        upsert_prompt(conn, "name", "v1")
        upsert_prompt(conn, "name", "v2")
        upsert_prompt(conn, "name", "v3")

        assert rollback_prompt(conn, "name", to_version=1) is True

        result = get_prompt(conn, "name")
        assert result is not None
        # Rollback creates a new version with the old template.
        assert result.template == "v1"
        assert result.version == 4
        assert result.updated_by == "rollback"

    def test_rollback_unknown_version_returns_false(self, conn: sqlite3.Connection) -> None:
        upsert_prompt(conn, "name", "only")
        assert rollback_prompt(conn, "name", to_version=99) is False
        result = get_prompt(conn, "name")
        assert result is not None
        assert result.template == "only"
