"""Helpers for normalizing malformed text from external sources."""

from __future__ import annotations

import sqlite3
from typing import Any

_REPLACEMENT_CHAR = "\ufffd"


def replace_lone_surrogates(value: str) -> str:
    """Replace any lone UTF-16 surrogate code units with U+FFFD."""
    if not value:
        return value

    if not any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        return value

    return "".join(_REPLACEMENT_CHAR if 0xD800 <= ord(char) <= 0xDFFF else char for char in value)


def sanitize_text(value: str | None) -> str | None:
    """Normalize malformed surrogate code units in optional text."""
    if value is None:
        return None
    return replace_lone_surrogates(value)


def row_value(row: sqlite3.Row | dict[str, Any], key: str, default: Any = None) -> Any:
    """Safely access a value from an sqlite3.Row or dict."""
    if isinstance(row, sqlite3.Row):
        try:
            return row[key]
        except (IndexError, KeyError):
            return default
    return row.get(key, default)


def sanitize_nested_strings(value: Any) -> Any:
    """Recursively normalize strings inside nested lists/dicts for JSON storage."""
    if isinstance(value, str):
        return replace_lone_surrogates(value)
    if isinstance(value, list):
        return [sanitize_nested_strings(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_nested_strings(item) for item in value)
    if isinstance(value, dict):
        return {sanitize_nested_strings(key): sanitize_nested_strings(item) for key, item in value.items()}
    return value


_TRUNCATION_SUFFIXES = ("\u2026", "...")


def looks_truncated_text(text: str | None) -> bool:
    """Check if text appears truncated (ends with ellipsis or '...')."""
    if not text:
        return False
    stripped = text.rstrip()
    return bool(stripped) and stripped.endswith(_TRUNCATION_SUFFIXES)
