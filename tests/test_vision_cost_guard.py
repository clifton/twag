"""Tests for stale-media cost guards and transactional vision accounting."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from click.testing import CliRunner

import twag.processor.triage as triage_mod
import twag.scorer.llm_client as llm_client_mod
import twag.scorer.scoring as scoring_mod
from twag.cli import cli
from twag.db import get_connection, init_db, insert_tweet, record_llm_usage
from twag.scorer import MediaAnalysisResult, TriageResult


def test_stale_tweets_are_triaged_without_vision(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "stale-vision.db"
    init_db(db_path)
    now = datetime.now(timezone.utc)

    with get_connection(db_path) as conn:
        for tweet_id, created_at in [
            ("stale", now - timedelta(days=10)),
            ("recent", now - timedelta(hours=2)),
        ]:
            assert insert_tweet(
                conn,
                tweet_id=tweet_id,
                author_handle="test",
                content=f"{tweet_id} media tweet",
                created_at=created_at,
                source="test",
                has_media=True,
                media_items=[{"url": f"https://example.com/{tweet_id}.png"}],
            )
        conn.commit()
        rows = conn.execute("SELECT * FROM tweets ORDER BY id").fetchall()

        monkeypatch.setattr(
            triage_mod,
            "load_config",
            lambda: {
                "llm": {
                    "max_concurrency_text": 1,
                    "max_concurrency_triage": 1,
                    "max_concurrency_vision": 1,
                    "vision_model": "gemini-3.7-flash",
                    "vision_provider": "gemini",
                },
                "scoring": {
                    "min_score_for_analysis": None,
                    "min_score_for_article_processing": 99,
                },
                "processing": {},
            },
        )
        monkeypatch.setattr(
            triage_mod,
            "triage_tweets_batch",
            lambda batch, model=None, provider=None, **kwargs: [
                TriageResult(
                    tweet_id=item["id"],
                    score=8,
                    categories=["news"],
                    summary="summary",
                )
                for item in batch
            ],
        )

        analyzed: list[str] = []

        def _fake_analyze_media(url, **_kwargs):
            analyzed.append(url)
            return MediaAnalysisResult(
                kind="chart",
                short_description="chart",
                prose_text="text",
                prose_summary="summary",
            )

        monkeypatch.setattr(triage_mod, "analyze_media", _fake_analyze_media)

        results = triage_mod._triage_rows(
            conn,
            tweet_rows=rows,
            batch_size=10,
            triage_model=None,
            enrich_model=None,
            high_threshold=7,
            tier1_handles=set(),
            update_stats=False,
            allow_summarize=False,
            media_min_score=5,
            vision_max_age_days=3,
        )
        conn.commit()

    assert len(results) == 2
    assert analyzed == ["https://example.com/recent.png"]
    with get_connection(db_path, readonly=True) as conn:
        stale = conn.execute("SELECT processed_at, media_analysis FROM tweets WHERE id = 'stale'").fetchone()
        recent = conn.execute("SELECT processed_at, media_analysis FROM tweets WHERE id = 'recent'").fetchone()
    assert stale["processed_at"] is not None
    assert stale["media_analysis"] is None
    assert recent["processed_at"] is not None
    assert recent["media_analysis"] is not None


def test_db_skip_stale_clears_only_old_backlog(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "twag.db"
    init_db(db_path)
    now = datetime.now(timezone.utc)

    with get_connection(db_path) as conn:
        assert insert_tweet(
            conn,
            tweet_id="old",
            author_handle="test",
            content="old backlog",
            created_at=now - timedelta(days=10),
            source="test",
        )
        assert insert_tweet(
            conn,
            tweet_id="new",
            author_handle="test",
            content="new backlog",
            created_at=now - timedelta(hours=1),
            source="test",
        )
        conn.commit()

    result = CliRunner().invoke(cli, ["db", "skip-stale", "--older-than-days", "3"])

    assert result.exit_code == 0
    assert "Marked 1 stale unprocessed tweets" in result.output
    with get_connection(db_path, readonly=True) as conn:
        old = conn.execute("SELECT processed_at, relevance_score, category FROM tweets WHERE id = 'old'").fetchone()
        new = conn.execute("SELECT processed_at FROM tweets WHERE id = 'new'").fetchone()
    assert old["processed_at"] is not None
    assert old["relevance_score"] == 0
    assert json.loads(old["category"]) == ["skipped_stale"]
    assert new["processed_at"] is None


@pytest.mark.parametrize(
    ("response_text", "parse_succeeds"),
    [
        (
            json.dumps(
                {
                    "kind": "chart",
                    "short_description": "Revenue chart",
                    "prose_text": "Revenue is 100",
                    "prose_summary": "Revenue rose",
                    "chart": {},
                    "table": {},
                },
            ),
            True,
        ),
        ("not valid json", False),
    ],
)
def test_gemini_vision_usage_is_recorded_even_when_parsing_fails(
    monkeypatch,
    tmp_path,
    response_text,
    parse_succeeds,
) -> None:
    db_path = tmp_path / "vision-usage.db"
    init_db(db_path)

    usage = SimpleNamespace(
        prompt_token_count=120,
        candidates_token_count=30,
        cached_content_token_count=10,
        thoughts_token_count=5,
        total_token_count=155,
    )
    response = SimpleNamespace(text=response_text, usage_metadata=usage)
    client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda **_kwargs: response,
        ),
    )
    image_response = SimpleNamespace(
        content=b"test-image",
        headers={"content-type": "image/png"},
        raise_for_status=lambda: None,
    )

    monkeypatch.setattr(scoring_mod, "load_config", lambda: {"llm": {}})
    monkeypatch.setattr(
        llm_client_mod,
        "load_config",
        lambda: {
            "llm": {
                "retry_max_attempts": 1,
                "retry_base_seconds": 0,
                "retry_max_seconds": 0,
                "retry_jitter": 0,
            },
        },
    )
    monkeypatch.setattr(llm_client_mod, "get_gemini_client", lambda: client)
    monkeypatch.setattr(httpx, "get", lambda *_args, **_kwargs: image_response)

    usage_records: list[dict] = []
    if parse_succeeds:
        result = scoring_mod.analyze_media(
            "https://example.com/chart.png",
            model="gemini-3.7-flash",
            provider="gemini",
            usage_recorder=usage_records.append,
        )
        assert result.kind == "chart"
    else:
        with pytest.raises(ValueError, match="Could not parse JSON"):
            scoring_mod.analyze_media(
                "https://example.com/chart.png",
                model="gemini-3.7-flash",
                provider="gemini",
                usage_recorder=usage_records.append,
            )

    assert len(usage_records) == 1
    with get_connection(db_path) as conn:
        record_llm_usage(conn=conn, **usage_records[0])
        conn.commit()

    with get_connection(db_path, readonly=True) as conn:
        row = conn.execute(
            """
            SELECT component, provider, model, input_tokens, output_tokens,
                   is_vision, success, estimated_cost_usd
            FROM llm_usage
            """,
        ).fetchone()
    assert row["component"] == "vision"
    assert row["provider"] == "gemini"
    assert row["model"] == "gemini-3.7-flash"
    assert row["input_tokens"] == 120
    assert row["output_tokens"] == 30
    assert row["is_vision"] == 1
    assert row["success"] == 1
    assert row["estimated_cost_usd"] > 0
