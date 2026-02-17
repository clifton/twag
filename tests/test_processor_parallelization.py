"""Tests for processor parallelization and enrichment throughput helpers."""

import threading
from datetime import datetime, timezone

import twag.processor.pipeline as pipeline_mod
import twag.processor.triage as triage_mod
from twag.db import get_connection, init_db, insert_tweet, update_tweet_processing
from twag.scorer import EnrichmentResult, TriageResult

# Fixed timestamp for deterministic test data.
_FIXED_TS = datetime(2025, 1, 1, tzinfo=timezone.utc)


def test_triage_overlap_with_summaries_using_dedicated_pool(monkeypatch, tmp_path) -> None:
    """Summary tasks should start before all triage batches finish.

    Uses event-based synchronization instead of wall-clock timing to avoid
    flakiness under CPU contention (CI, heavy load).
    """
    db_path = tmp_path / "triage_parallel.db"
    init_db(db_path)

    with get_connection(db_path) as conn:
        for idx in range(1, 3):
            inserted = insert_tweet(
                conn,
                tweet_id=f"tweet-{idx}",
                author_handle=f"acct{idx}",
                content=f"Long content {idx} " + ("x" * 700),
                created_at=_FIXED_TS,
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

        # Event-based synchronization: track whether a summary was submitted
        # before triage batch 2 completed.
        summary_started = threading.Event()
        triage_2_done = threading.Event()
        summary_before_triage_2 = threading.Event()

        def _fake_triage_tweets_batch(batch, model=None, provider=None):
            tweet_id = batch[0]["id"]
            batch_no = 1 if tweet_id == "tweet-1" else 2
            if batch_no == 2:
                # Block batch 2 briefly so the summary task can start first.
                summary_started.wait(timeout=5)
                triage_2_done.set()
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
            summary_started.set()
            if not triage_2_done.is_set():
                summary_before_triage_2.set()
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
        assert summary_started.is_set(), "summarize_tweet was never called"
        assert summary_before_triage_2.is_set(), "summary should have started before triage batch 2 completed"


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
            created_at=_FIXED_TS,
            source="test",
        )
        assert inserted_quote is True

        inserted_main = insert_tweet(
            conn,
            tweet_id="main-1",
            author_handle="mainacct",
            content="Main tweet content",
            created_at=_FIXED_TS,
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
