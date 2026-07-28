"""Tests for persistent media analysis caching."""

import sqlite3

import pytest

import twag.processor.triage as triage_mod
from twag.db import get_cached_media_analysis, get_connection, init_db, record_media_analysis
from twag.scorer import MediaAnalysisResult


def test_record_and_read_media_analysis_cache(tmp_path) -> None:
    db_path = tmp_path / "media-cache.db"
    init_db(db_path)

    record_media_analysis(
        "https://example.com/chart.png",
        provider="gemini",
        model="gemini-3-flash-preview",
        result={
            "kind": "chart",
            "short_description": "Chart",
            "prose_text": "Revenue 100",
            "prose_summary": "Revenue rises",
            "chart": {"insight": "Up"},
            "table": {},
        },
        db_path=db_path,
    )

    cached = get_cached_media_analysis(
        "https://example.com/chart.png",
        provider="gemini",
        model="gemini-3-flash-preview",
        db_path=db_path,
    )

    assert cached is not None
    assert cached["kind"] == "chart"
    assert cached["chart"]["insight"] == "Up"


def test_cache_write_uses_callers_locked_transaction(tmp_path) -> None:
    """The cache row must not need a competing writer or commit early."""
    db_path = tmp_path / "media-cache-transaction.db"
    init_db(db_path)

    with get_connection(db_path) as batch_conn:
        batch_conn.execute(
            """
            INSERT INTO tweets (id, author_handle, content, created_at)
            VALUES ('batch-1', 'test', 'holds write lock', CURRENT_TIMESTAMP)
            """,
        )
        record_media_analysis(
            "https://example.com/transactional.png",
            provider="gemini",
            model="gemini-3-flash-preview",
            result={"kind": "chart"},
            conn=batch_conn,
        )

        with get_connection(db_path, readonly=True) as read_conn:
            invisible = read_conn.execute(
                "SELECT 1 FROM media_analysis_cache WHERE media_url = ?",
                ("https://example.com/transactional.png",),
            ).fetchone()
        assert invisible is None

        competing_conn = sqlite3.connect(db_path, timeout=0.01)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                competing_conn.execute(
                    """
                    INSERT INTO media_analysis_cache (
                        media_url, provider, model, result_json
                    ) VALUES ('https://example.com/blocked.png', 'gemini', 'model', '{}')
                    """,
                )
        finally:
            competing_conn.close()

        batch_conn.commit()

    cached = get_cached_media_analysis(
        "https://example.com/transactional.png",
        provider="gemini",
        model="gemini-3-flash-preview",
        db_path=db_path,
    )
    assert cached == {"kind": "chart"}


def test_analyze_media_items_reuses_cache(monkeypatch) -> None:
    cache = {
        "https://example.com/cached.png": {
            "kind": "chart",
            "short_description": "Cached chart",
            "prose_text": "Cached text",
            "prose_summary": "Cached summary",
            "chart": {"insight": "Cached"},
            "table": {},
        },
    }
    analyzed_urls: list[str] = []
    recorded_urls: list[str] = []

    monkeypatch.setattr(
        triage_mod,
        "load_config",
        lambda: {
            "llm": {
                "vision_model": "gemini-3-flash-preview",
                "vision_provider": "gemini",
            },
        },
    )

    def _get_cached_media_analysis(url, *, provider, model):
        return cache.get(url)

    def _record_media_analysis(url, *, provider, model, result) -> None:
        recorded_urls.append(url)

    monkeypatch.setattr(triage_mod, "get_cached_media_analysis", _get_cached_media_analysis)
    monkeypatch.setattr(triage_mod, "record_media_analysis", _record_media_analysis)
    monkeypatch.setattr(triage_mod, "increment_media_analysis_cache_hit", lambda *args, **kwargs: None)

    def _fake_analyze_media(url, model=None, provider=None):
        analyzed_urls.append(url)
        return MediaAnalysisResult(
            kind="table",
            short_description="Fresh table",
            prose_text="Fresh text",
            prose_summary="Fresh summary",
            chart={},
            table={"summary": "Fresh"},
        )

    monkeypatch.setattr(triage_mod, "analyze_media", _fake_analyze_media)

    items, updated = triage_mod._analyze_media_items(
        [
            {"url": "https://example.com/cached.png"},
            {"url": "https://example.com/fresh.png"},
        ],
    )

    assert updated is True
    assert analyzed_urls == ["https://example.com/fresh.png"]
    assert recorded_urls == ["https://example.com/fresh.png"]
    assert items[0]["short_description"] == "Cached chart"
    assert items[1]["short_description"] == "Fresh table"


def test_media_analysis_cache_migrates_with_init_db(tmp_path) -> None:
    db_path = tmp_path / "schema.db"
    init_db(db_path)

    with get_connection(db_path, readonly=True) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='media_analysis_cache'",
        ).fetchone()

    assert row is not None
