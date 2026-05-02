"""Persistent cache for media analysis results."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

from .connection import commit_with_retry, get_connection

log = logging.getLogger(__name__)

MEDIA_ANALYSIS_CACHE_SQL = """
CREATE TABLE IF NOT EXISTS media_analysis_cache (
    media_url TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    result_json TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (media_url, provider, model)
);
CREATE INDEX IF NOT EXISTS idx_media_analysis_cache_updated
ON media_analysis_cache(updated_at DESC);
"""


def ensure_media_analysis_cache_table(conn: sqlite3.Connection) -> None:
    """Create the media analysis cache table."""
    conn.executescript(MEDIA_ANALYSIS_CACHE_SQL)


def _normalize_key(value: str | None) -> str:
    return (value or "").strip().lower()


def get_cached_media_analysis(
    media_url: str,
    *,
    provider: str | None,
    model: str | None,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    """Return cached media analysis for a URL/provider/model, if present."""
    url = (media_url or "").strip()
    provider_key = _normalize_key(provider)
    model_key = _normalize_key(model)
    if not url or not provider_key or not model_key:
        return None

    try:
        with get_connection(db_path, readonly=True) as conn:
            row = conn.execute(
                """
                SELECT result_json
                FROM media_analysis_cache
                WHERE media_url = ? AND provider = ? AND model = ?
                """,
                (url, provider_key, model_key),
            ).fetchone()
        if row is None:
            return None
        data = json.loads(row["result_json"])
        return data if isinstance(data, dict) else None
    except Exception:
        log.debug("Failed to read media analysis cache", exc_info=True)
        return None


def record_media_analysis(
    media_url: str,
    *,
    provider: str | None,
    model: str | None,
    result: dict[str, Any],
    db_path: Path | None = None,
) -> None:
    """Persist a media analysis result; cache failures do not affect processing."""
    url = (media_url or "").strip()
    provider_key = _normalize_key(provider)
    model_key = _normalize_key(model)
    if not url or not provider_key or not model_key:
        return

    try:
        payload = json.dumps(result, sort_keys=True)
        now = datetime.now(timezone.utc).isoformat()
        with get_connection(db_path) as conn:
            ensure_media_analysis_cache_table(conn)
            conn.execute(
                """
                INSERT INTO media_analysis_cache (
                    media_url, provider, model, result_json, hit_count, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(media_url, provider, model) DO UPDATE SET
                    result_json = excluded.result_json,
                    updated_at = excluded.updated_at
                """,
                (url, provider_key, model_key, payload, now, now),
            )
            commit_with_retry(conn)
    except Exception:
        log.debug("Failed to write media analysis cache", exc_info=True)


def increment_media_analysis_cache_hit(
    media_url: str,
    *,
    provider: str | None,
    model: str | None,
    db_path: Path | None = None,
) -> None:
    """Best-effort increment for cache hit observability."""
    url = (media_url or "").strip()
    provider_key = _normalize_key(provider)
    model_key = _normalize_key(model)
    if not url or not provider_key or not model_key:
        return

    try:
        with get_connection(db_path) as conn:
            conn.execute(
                """
                UPDATE media_analysis_cache
                SET hit_count = hit_count + 1,
                    updated_at = ?
                WHERE media_url = ? AND provider = ? AND model = ?
                """,
                (datetime.now(timezone.utc).isoformat(), url, provider_key, model_key),
            )
            commit_with_retry(conn)
    except Exception:
        log.debug("Failed to update media analysis cache hit count", exc_info=True)
