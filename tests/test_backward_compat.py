"""Backward-compatibility test suite.

Verifies that public exports, deprecated aliases, legacy data formats,
and database migrations continue to work as expected.
"""

from __future__ import annotations

import importlib
import json
import re
import sqlite3
import warnings

import pytest

# ---------------------------------------------------------------------------
# (a) Import smoke tests - every name in __all__ must be importable
# ---------------------------------------------------------------------------

_MODULES_WITH_ALL = [
    "twag.models",
    "twag.db",
    "twag.processor",
    "twag.scorer",
    "twag.fetcher",
]


@pytest.mark.parametrize("module_name", _MODULES_WITH_ALL)
def test_all_exports_importable(module_name: str) -> None:
    """Every name listed in __all__ should be importable from the package."""
    mod = importlib.import_module(module_name)
    all_names = getattr(mod, "__all__", [])
    assert all_names, f"{module_name} has no __all__"
    for name in all_names:
        obj = getattr(mod, name, None)
        assert obj is not None, f"{module_name}.{name} listed in __all__ but not importable"


# ---------------------------------------------------------------------------
# (b) Deprecated alias tests
# ---------------------------------------------------------------------------


def test_get_memory_dir_emits_deprecation(tmp_path, monkeypatch):
    """get_memory_dir() should emit DeprecationWarning and return data dir."""
    monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))
    from twag.config import get_data_dir, get_memory_dir

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = get_memory_dir()

    assert result == get_data_dir()
    assert len(w) == 1
    assert issubclass(w[0].category, DeprecationWarning)
    assert "get_memory_dir" in str(w[0].message)


def test_get_workspace_path_emits_deprecation(tmp_path, monkeypatch):
    """get_workspace_path() should emit DeprecationWarning and return data dir."""
    monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))
    from twag.config import get_data_dir, get_workspace_path

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = get_workspace_path()

    assert result == get_data_dir()
    assert len(w) == 1
    assert issubclass(w[0].category, DeprecationWarning)
    assert "get_workspace_path" in str(w[0].message)


# ---------------------------------------------------------------------------
# (c) Legacy category format handling
# ---------------------------------------------------------------------------


def _parse_categories(raw: str | None) -> list[str]:
    """Reproduce the category parsing logic used in search/web routes."""
    if not raw:
        return []
    try:
        categories = json.loads(raw)
        if isinstance(categories, str):
            categories = [categories]
    except json.JSONDecodeError:
        categories = [raw]
    return categories


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('["fed_policy","rates_fx"]', ["fed_policy", "rates_fx"]),
        ('"fed_policy"', ["fed_policy"]),
        ("fed_policy", ["fed_policy"]),
        (None, []),
        ("", []),
    ],
    ids=["json_array", "json_string", "plain_string", "none", "empty"],
)
def test_category_parsing(raw: str | None, expected: list[str]) -> None:
    """Category column must parse regardless of legacy format."""
    assert _parse_categories(raw) == expected


def test_category_sql_filter_both_formats() -> None:
    """SQL filter clause matches both JSON-array and plain-string rows."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, category TEXT)")
    conn.execute("INSERT INTO t VALUES (1, ?)", ('["fed_policy","rates_fx"]',))
    conn.execute("INSERT INTO t VALUES (2, ?)", ("fed_policy",))
    conn.execute("INSERT INTO t VALUES (3, ?)", ('["rates_fx"]',))
    conn.commit()

    category = "fed_policy"
    rows = conn.execute(
        "SELECT id FROM t WHERE (category LIKE ? OR category = ?)",
        (f'%"{category}"%', category),
    ).fetchall()
    ids = {r[0] for r in rows}
    assert ids == {1, 2}


# ---------------------------------------------------------------------------
# (d) Legacy retweet text format handling
# ---------------------------------------------------------------------------


# Mirror the regex from twag/web/routes/tweets.py
LEGACY_RETWEET_RE = re.compile(r"^\s*RT\s+@([A-Za-z0-9_]{1,15}):\s*(.+)$")


@pytest.mark.parametrize(
    "text, expected_handle, expected_content",
    [
        ("RT @elonmusk: Big news today!", "elonmusk", "Big news today!"),
        ("  RT @user123: Some content here", "user123", "Some content here"),
    ],
)
def test_legacy_retweet_regex_matches(text: str, expected_handle: str, expected_content: str) -> None:
    """Legacy RT-form text should be parsed into handle and content."""
    match = LEGACY_RETWEET_RE.match(text)
    assert match is not None
    assert match.group(1) == expected_handle
    assert match.group(2).strip() == expected_content


@pytest.mark.parametrize(
    "text",
    [
        "Just a normal tweet mentioning RT @someone",
        "Not a retweet at all",
        "",
    ],
)
def test_legacy_retweet_regex_no_match(text: str) -> None:
    """Non-RT text should not match the legacy retweet pattern."""
    assert LEGACY_RETWEET_RE.match(text) is None


# ---------------------------------------------------------------------------
# (e) Database migration idempotency
# ---------------------------------------------------------------------------


def test_migrations_idempotent(tmp_path, monkeypatch) -> None:
    """Running _run_migrations twice on the same database must not error."""
    monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))

    from twag.db.connection import _run_migrations, get_connection
    from twag.db.schema import SCHEMA

    db_path = tmp_path / "twag.db"
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)
        _run_migrations(conn)
        conn.commit()

    # Run migrations a second time — should be a no-op, not raise
    with get_connection(db_path) as conn:
        _run_migrations(conn)
        conn.commit()

    # Verify core tables still exist
    with get_connection(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "tweets" in tables
        assert "accounts" in tables
        assert "fetch_log" in tables
