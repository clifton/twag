"""Tests for processor parallelization and enrichment throughput helpers."""

import threading
import time
from datetime import datetime, timezone

import twag.processor.pipeline as pipeline_mod
import twag.processor.triage as triage_mod
from twag.db import get_connection, init_db, insert_tweet, update_tweet_processing
from twag.scorer import EnrichmentResult, TriageResult


def test_triage_overlap_with_summaries_using_dedicated_pool(monkeypatch, tmp_path) -> None:
    """Summary tasks should run before all triage batches fully complete."""
    db_path = tmp_path / "triage_parallel.db"
    init_db(db_path)

    with get_connection(db_path) as conn:
        for idx in range(1, 3):
            inserted = insert_tweet(
                conn,
                tweet_id=f"tweet-{idx}",
                author_handle=f"acct{idx}",
                content=f"Long content {idx} " + ("x" * 700),
                created_at=datetime.now(timezone.utc),
                source="test",
            )
            assert inserted is True
        conn.commit()

        rows = conn.execute("SELECT * FROM tweets ORDER BY id ASC").fetchall()

        monkeypatch.setattr(
            triage_mod,
            "load_config",
            lambda: {
                "llm": {
                    "max_concurrency_text": 1,
                    "max_concurrency_triage": 1,
                    "max_concurrency_vision": 1,
                    "vision_model": None,
                    "vision_provider": None,
                },
                "scoring": {
                    "min_score_for_analysis": 99,
                    "min_score_for_article_processing": 99,
                },
            },
        )

        events: dict[str, float] = {}
        summary_starts: list[float] = []
        lock = threading.Lock()

        def _fake_triage_tweets_batch(batch, model=None, provider=None):
            tweet_id = batch[0]["id"]
            batch_no = 1 if tweet_id == "tweet-1" else 2
            with lock:
                events[f"triage_{batch_no}_start"] = time.perf_counter()
            time.sleep(0.04 if batch_no == 1 else 0.18)
            with lock:
                events[f"triage_{batch_no}_end"] = time.perf_counter()
            return [
                TriageResult(
                    tweet_id=item["id"],
                    score=6.0,
                    categories=["news"],
                    summary="scored",
                )
                for item in batch
            ]

        def _fake_summarize_tweet(tweet_text, handle, model=None, provider=None):
            with lock:
                summary_starts.append(time.perf_counter())
            time.sleep(0.03)
            return f"summary for @{handle}"

        monkeypatch.setattr(triage_mod, "triage_tweets_batch", _fake_triage_tweets_batch)
        monkeypatch.setattr(triage_mod, "summarize_tweet", _fake_summarize_tweet)

        results = triage_mod._triage_rows(
            conn,
            tweet_rows=rows,
            batch_size=1,
            triage_model=None,
            enrich_model=None,
            high_threshold=7.0,
            tier1_handles=set(),
            update_stats=False,
            allow_summarize=True,
            media_min_score=None,
        )

        assert len(results) == 2
        assert summary_starts
        assert "triage_2_end" in events
        assert summary_starts[0] < events["triage_2_end"]


def test_enrich_high_signal_prefers_local_quote_row(monkeypatch, tmp_path) -> None:
    """Enrichment should use quoted tweet content from local DB when available."""
    db_path = tmp_path / "enrich_local_quote.db"
    init_db(db_path)

    with get_connection(db_path) as conn:
        inserted_quote = insert_tweet(
            conn,
            tweet_id="quote-1",
            author_handle="quotedacct",
            content="Quoted local context",
            created_at=datetime.now(timezone.utc),
            source="test",
        )
        assert inserted_quote is True

        inserted_main = insert_tweet(
            conn,
            tweet_id="main-1",
            author_handle="mainacct",
            content="Main tweet content",
            created_at=datetime.now(timezone.utc),
            source="test",
            has_quote=True,
            quote_tweet_id="quote-1",
        )
        assert inserted_main is True

        update_tweet_processing(
            conn,
            tweet_id="main-1",
            relevance_score=9.0,
            categories=["news"],
            summary="summary",
            signal_tier="high_signal",
            tickers=[],
        )
        conn.commit()

    monkeypatch.setattr(pipeline_mod, "get_connection", lambda readonly=False: get_connection(db_path))
    monkeypatch.setattr(
        pipeline_mod,
        "load_config",
        lambda: {
            "scoring": {"high_signal_threshold": 7},
            "llm": {"max_concurrency_text": 1},
        },
    )
    monkeypatch.setattr(
        pipeline_mod,
        "read_tweet",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("read_tweet should not be called")),
    )

    seen: dict[str, str] = {}

    def _fake_enrich_tweet(
        tweet_text: str,
        handle: str,
        author_category: str,
        quoted_tweet: str,
        article_summary: str,
        image_description: str,
        model=None,
    ) -> EnrichmentResult:
        seen["quoted_tweet"] = quoted_tweet
        return EnrichmentResult(
            signal_tier="high_signal",
            insight="insight",
            implications="implications",
            narratives=[],
            tickers=[],
        )

    monkeypatch.setattr(pipeline_mod, "enrich_tweet", _fake_enrich_tweet)

    results = pipeline_mod.enrich_high_signal(limit=5, enrich_model="dummy-model")

    assert len(results) == 1
    assert seen["quoted_tweet"] == "@quotedacct: Quoted local context"
