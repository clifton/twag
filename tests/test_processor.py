"""Tests for process-time URL expansion behavior."""

import json
from datetime import datetime, timezone

import twag.processor as processor_mod
from twag.db import get_connection, get_tweet_by_id, init_db, insert_tweet


def test_process_unprocessed_expands_links_and_persists_before_triage(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "twag_process_expand_links.db"
    init_db(db_path)

    with get_connection(db_path) as conn:
        inserted = insert_tweet(
            conn,
            tweet_id="1001",
            author_handle="root_user",
            content="Interesting thread https://t.co/ext",
            created_at=datetime.now(timezone.utc),
            source="test",
            has_link=True,
            links=[{"url": "https://t.co/ext", "expanded_url": "https://t.co/ext"}],
        )
        assert inserted is True
        conn.commit()

    monkeypatch.setattr(processor_mod, "get_connection", lambda: get_connection(db_path))
    monkeypatch.setattr(
        processor_mod,
        "load_config",
        lambda: {
            "scoring": {
                "batch_size": 10,
                "high_signal_threshold": 7,
                "min_score_for_media": 3,
            },
            "fetch": {"quote_depth": 0, "quote_delay": 0.0},
            "processing": {"max_concurrency_url_expansion": 4},
        },
    )

    calls: list[list[dict]] = []

    def _fake_expand_links(links: list[dict]) -> list[dict]:
        calls.append(links)
        return [
            {
                "url": "https://t.co/ext",
                "expanded_url": "https://github.com/example/project",
                "display_url": "github.com/example/project",
            }
        ]

    captured_rows: list[dict] = []

    def _fake_triage_rows(_conn, **kwargs):
        tweet_rows = kwargs["tweet_rows"]
        captured_rows.extend(tweet_rows)
        return []

    monkeypatch.setattr(processor_mod, "expand_links_in_place", _fake_expand_links)
    monkeypatch.setattr(processor_mod, "_triage_rows", _fake_triage_rows)

    results = processor_mod.process_unprocessed(limit=10)

    assert results == []
    assert len(calls) == 1
    assert len(captured_rows) == 1

    triage_row = captured_rows[0]
    triage_links = json.loads(triage_row["links_json"])
    assert triage_links[0]["expanded_url"] == "https://github.com/example/project"
    assert triage_row["links_expanded_at"] is not None

    with get_connection(db_path) as conn:
        row = get_tweet_by_id(conn, "1001")
        assert row is not None
        parsed = json.loads(row["links_json"])
        assert parsed[0]["expanded_url"] == "https://github.com/example/project"
        assert row["links_expanded_at"] is not None


def test_process_unprocessed_skips_already_expanded_links(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "twag_process_skip_expanded_links.db"
    init_db(db_path)

    with get_connection(db_path) as conn:
        inserted = insert_tweet(
            conn,
            tweet_id="1002",
            author_handle="root_user",
            content="Already expanded https://github.com/example/project",
            created_at=datetime.now(timezone.utc),
            source="test",
            has_link=True,
            links=[
                {
                    "url": "https://t.co/ext",
                    "expanded_url": "https://github.com/example/project",
                    "display_url": "github.com/example/project",
                }
            ],
        )
        assert inserted is True
        expanded_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE tweets SET links_expanded_at = ? WHERE id = ?",
            (expanded_at, "1002"),
        )
        conn.commit()

    monkeypatch.setattr(processor_mod, "get_connection", lambda: get_connection(db_path))
    monkeypatch.setattr(
        processor_mod,
        "load_config",
        lambda: {
            "scoring": {
                "batch_size": 10,
                "high_signal_threshold": 7,
                "min_score_for_media": 3,
            },
            "fetch": {"quote_depth": 0, "quote_delay": 0.0},
            "processing": {"max_concurrency_url_expansion": 4},
        },
    )
    monkeypatch.setattr(
        processor_mod,
        "expand_links_in_place",
        lambda _links: (_ for _ in ()).throw(AssertionError("expand_links_in_place should not run")),
    )
    monkeypatch.setattr(processor_mod, "_triage_rows", lambda _conn, **_kwargs: [])

    processor_mod.process_unprocessed(limit=10)

    with get_connection(db_path) as conn:
        row = get_tweet_by_id(conn, "1002")
        assert row is not None
        assert row["links_expanded_at"] == expanded_at
