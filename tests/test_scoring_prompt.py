"""Regression tests for surprise-first triage prompt plumbing."""

import os

from twag.db import get_connection, init_db, upsert_prompt
from twag.metrics import get_collector
from twag.scorer import (
    TRIAGE_BATCH_SCHEMA,
    load_fund_context,
    render_triage_prompt,
    resolve_triage_template,
    triage_tweets_batch,
)
from twag.scorer.prompts import BATCH_TRIAGE_PROMPT


def test_prompt_render_uses_literal_replacement_and_preserves_json_braces():
    template = 'schema={"literal":{"brace":true}} {fund_context} {categories} {tweets}'
    rendered = render_triage_prompt(template, tweets="tweet-lines", fund_context="book", categories="macro")
    assert rendered == 'schema={"literal":{"brace":true}} book macro tweet-lines'


def test_prompt_contains_author_context_fund_context_and_categories(monkeypatch):
    captured = {}

    def fake_call(provider, model, prompt, **kwargs):
        captured.update(prompt=prompt, kwargs=kwargs)
        return (
            '[{"id":"1","score":7,"surprise":1,"is_stale_repeat":false,'
            '"categories":["macro_data"],"themes":["ai-memory"],"playbook_trigger":"none",'
            '"catalyst":"none","direction":"long","tickers":["MU"],"summary":"fact"}]'
        )

    monkeypatch.setattr("twag.scorer.scoring._call_llm", fake_call)
    results = triage_tweets_batch(
        [{"id": "1", "handle": "source", "text": "new print", "author_context": "tier-1, macro, prior 7.2"}],
        model="model",
        provider="gemini",
        fund_context="LIVE THEMES: ai-memory",
    )

    assert "@source (tier-1, macro, prior 7.2): new print" in captured["prompt"]
    assert "LIVE THEMES: ai-memory" in captured["prompt"]
    assert "fed_policy, inflation" in captured["prompt"]
    assert captured["kwargs"]["json_schema"] is TRIAGE_BATCH_SCHEMA
    assert results[0].playbook_trigger is None
    assert results[0].catalyst_status is None


def test_parser_tolerates_old_missing_fields(monkeypatch):
    monkeypatch.setattr(
        "twag.scorer.scoring._call_llm",
        lambda *args, **kwargs: '[{"id":"old","score":5,"categories":["equities"],"summary":"legacy"}]',
    )
    result = triage_tweets_batch(
        [{"id": "old", "handle": "old", "text": "legacy"}],
        model="model",
        provider="anthropic",
    )[0]
    assert result.surprise == 0
    assert result.is_stale_repeat is False
    assert result.themes == []
    assert result.playbook_trigger is None
    assert result.catalyst_status is None
    assert result.direction == "na"


def test_strict_schema_uses_deepseek_compatible_required_sentinels():
    item_schema = TRIAGE_BATCH_SCHEMA["items"]
    assert set(item_schema["required"]) == set(item_schema["properties"])
    assert item_schema["additionalProperties"] is False
    assert item_schema["properties"]["playbook_trigger"]["enum"][-1] == "none"
    assert item_schema["properties"]["catalyst"]["enum"][-1] == "none"


def test_invalid_db_prompt_falls_back_and_records_metric(tmp_path):
    db_path = tmp_path / "twag.db"
    init_db(db_path)
    with get_connection(db_path) as conn:
        upsert_prompt(conn, "batch_triage", "bad {tweets}", updated_by="test")
        conn.commit()
        before = get_collector().counter_value("pipeline.triage.prompt_fallback")
        resolved = resolve_triage_template(conn)
    assert resolved == BATCH_TRIAGE_PROMPT
    assert get_collector().counter_value("pipeline.triage.prompt_fallback") == before + 1


def test_load_fund_context_rejects_stale_file(tmp_path):
    context = tmp_path / "twag-context.md"
    context.write_text("stale")
    os.utime(context, (1, 1))
    assert load_fund_context(context, max_age_seconds=60) == ("", True)

    context.write_text("fresh")
    assert load_fund_context(context, max_age_seconds=60) == ("fresh", False)


def test_generated_spine_context_wins_over_stopgap(monkeypatch, tmp_path):
    import twag.scorer.scoring as scoring

    stopgap = tmp_path / "twag-context.md"
    generated = tmp_path / "CONTEXT.md"
    stopgap.write_text("stopgap")
    generated.write_text("generated")
    os.utime(stopgap, (1, 1))
    monkeypatch.setattr(scoring, "FUND_CONTEXT_PATH", stopgap)
    monkeypatch.setattr(scoring, "GENERATED_FUND_CONTEXT_PATH", generated)
    assert load_fund_context(max_age_seconds=60) == ("generated", False)


def test_builtin_prompt_has_exact_three_placeholders():
    assert {
        placeholder
        for placeholder in ("{tweets}", "{fund_context}", "{categories}")
        if placeholder in BATCH_TRIAGE_PROMPT
    } == {
        "{tweets}",
        "{fund_context}",
        "{categories}",
    }
