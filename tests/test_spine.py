"""Signal-event v1 mapping and idempotency tests."""

from datetime import datetime, timezone

from twag.db import get_connection, init_db, insert_tweet, update_tweet_processing
from twag.spine import append_signal_event, build_signal_event, emit_signals, signal_kind, signal_materiality


def _row(**overrides):
    base = {
        "id": "2077639183712055354",
        "author_handle": "source",
        "content": "FOMC on 2026-07-30 adds a dated catalyst",
        "summary": "FOMC on 2026-07-30 adds a dated catalyst",
        "created_at": "2026-07-16T14:05:00+00:00",
        "processed_at": "2026-07-16T14:06:00+00:00",
        "relevance_score": 8,
        "surprise": 1,
        "themes": '["rates-inflation-wave","new:emergent"]',
        "tickers": '["ZN"]',
        "playbook_trigger": None,
        "catalyst_status": "scheduled",
        "direction": "short",
    }
    return {**base, **overrides}


def test_kind_and_materiality_mapping():
    assert signal_kind(8, 2, "resolved", catalyst_ref="x") == "surprise"
    assert signal_kind(8, 1, "resolved", catalyst_ref="x") == "catalyst_resolved"
    assert signal_kind(8, 1, "resolved") == "datapoint"
    assert signal_materiality(9, None) == 3
    assert signal_materiality(7, "supply_shock") == 3
    assert signal_materiality(8, None) == 2
    assert signal_materiality(7, None) == 1


def test_build_event_matches_shared_schema_contract():
    context = "UPCOMING CATALYSTS (14d): 2026-07-30 FOMC · 2026-08-01 NFP"
    event = build_signal_event(_row(), fund_context=context)
    assert event["id"].startswith("sig_")
    assert event["source"] == "twag_digest"
    assert event["kind"] == "catalyst_scheduled"
    assert event["catalyst_ref"] == "fomc:us:2026-07-30"
    assert event["catalyst_date"] == "2026-07-30"
    assert event["catalyst_type"] == "fomc"
    assert event["direction"] == "short"
    assert event["themes"] == ["rates-inflation-wave"]
    assert event["dedup_key"] == "tweet:2077639183712055354"
    assert event["correspondence"] is None
    assert event["action_item"] is None
    assert "story_key" not in event


def test_playbook_names_map_to_canonical_schema():
    event = build_signal_event(_row(playbook_trigger="supply_shock", catalyst_status=None))
    assert event["playbook_trigger"] == "supply_loss"
    assert event["materiality"] == 3


def test_resolved_catalyst_requires_one_registry_match(tmp_path):
    (tmp_path / "catalysts.json").write_text(
        '{"catalysts":[{"id":"corporate_action-mstr-2026-06-29","date":"2026-06-29",'
        '"type":"corporate_action","themes":["crypto-dat"],"instruments":["MSTR"]}]}',
    )
    event = build_signal_event(
        _row(
            content="Framework resolves stress",
            summary="Framework resolves stress",
            catalyst_status="resolved",
            themes='["crypto-dat"]',
            tickers='["MSTR"]',
        ),
        registry_dir=tmp_path,
    )
    assert event["kind"] == "catalyst_resolved"
    assert event["catalyst_ref"] == "corporate_action-mstr-2026-06-29"


def test_append_signal_event_uses_bounded_spine_cli(monkeypatch):
    captured = {}

    class Result:
        returncode = 0
        stdout = "appended: sig_ABC"
        stderr = ""

    def fake_run(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        return Result()

    monkeypatch.setattr("twag.spine.shutil.which", lambda name: "/usr/local/bin/spine")
    monkeypatch.setattr("twag.spine.subprocess.run", fake_run)
    append_signal_event(build_signal_event(_row(playbook_trigger="supply_shock", catalyst_status=None)))
    assert captured["command"][:3] == ["/usr/local/bin/spine", "signal", "append"]
    assert "--dedup-key" in captured["command"]
    assert "tweet:2077639183712055354" in captured["command"]
    assert captured["kwargs"]["timeout"] == 60
    assert captured["kwargs"]["check"] is False


def test_emit_is_idempotent_and_selects_utc_month(tmp_path):
    db_path = tmp_path / "twag.db"
    appended = []
    init_db(db_path)
    created = datetime(2026, 7, 31, 23, 59, tzinfo=timezone.utc)
    with get_connection(db_path) as conn:
        insert_tweet(conn, "tweet-1", "source", "new fact", created_at=created)
        update_tweet_processing(
            conn,
            "tweet-1",
            9,
            ["macro_data"],
            "new fact",
            "high_signal",
            ["ZN"],
            surprise=2,
            themes=["rates-inflation-wave"],
            direction="short",
        )
        conn.commit()
        now = datetime.now(timezone.utc)
        first = emit_signals(conn, now=now, fund_context="", append_event=appended.append)
        second = emit_signals(conn, now=now, fund_context="", append_event=appended.append)

    assert len(first) == 1
    assert second == []
    assert len(appended) == 1
    assert appended[0]["ts"].startswith("2026-07-31T23:59")
    assert appended[0]["dedup_key"] == "tweet:tweet-1"
