"""Tests for processor parallelization and enrichment throughput helpers."""

import threading
from contextlib import contextmanager
from datetime import datetime, timezone

import twag.processor.dependencies as deps_mod
import twag.processor.pipeline as pipeline_mod
import twag.processor.triage as triage_mod
from twag.db import get_connection, init_db, insert_tweet, update_tweet_processing
from twag.scorer import EnrichmentResult, TriageResult, XArticleSummaryResult

# Fixed timestamp for deterministic test data.
_FIXED_TS = datetime(2025, 1, 1, tzinfo=timezone.utc)


class _ThreadCheckingConnection:
    """Proxy that fails if DB access escapes the owner thread."""

    def __init__(self, conn) -> None:
        self._conn = conn
        self._owner_thread = threading.get_ident()
        self.write_calls = 0

    def _assert_owner_thread(self) -> None:
        assert threading.get_ident() == self._owner_thread, "SQLite access escaped the owner thread"

    def _track_write(self, sql: str) -> None:
        statement = sql.lstrip().upper()
        if statement.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
            self.write_calls += 1

    def execute(self, sql, parameters=()):
        self._assert_owner_thread()
        self._track_write(sql)
        return self._conn.execute(sql, parameters)

    def executemany(self, sql, seq_of_parameters):
        self._assert_owner_thread()
        self._track_write(sql)
        return self._conn.executemany(sql, seq_of_parameters)

    def __getattr__(self, name):
        return getattr(self._conn, name)


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


def test_triage_parallel_db_access_stays_on_owner_thread(monkeypatch, tmp_path) -> None:
    """Parallel triage workers should return data only; DB access stays local."""
    db_path = tmp_path / "triage_owner_thread.db"
    init_db(db_path)

    with get_connection(db_path) as raw_conn:
        inserted = insert_tweet(
            raw_conn,
            tweet_id="article-1",
            author_handle="analyst",
            content="Long article tweet " + ("x" * 700),
            created_at=_FIXED_TS,
            source="test",
            has_media=True,
            media_items=[{"url": "https://example.com/chart.png"}],
            has_link=True,
            is_x_article=True,
            article_title="Capex Outlook",
            article_preview="Preview",
            article_text="Article body " * 100,
            links=[{"url": "https://example.com/article", "expanded_url": "https://example.com/article"}],
        )
        assert inserted is True
        raw_conn.commit()

        rows = raw_conn.execute("SELECT * FROM tweets WHERE id = ?", ("article-1",)).fetchall()
        conn = _ThreadCheckingConnection(raw_conn)

        monkeypatch.setattr(
            triage_mod,
            "load_config",
            lambda: {
                "llm": {
                    "max_concurrency_text": 2,
                    "max_concurrency_triage": 2,
                    "max_concurrency_vision": 2,
                    "vision_model": None,
                    "vision_provider": None,
                },
                "scoring": {
                    "min_score_for_analysis": 3,
                    "min_score_for_article_processing": 5,
                },
            },
        )
        monkeypatch.setattr(
            triage_mod,
            "triage_tweets_batch",
            lambda batch, model=None, provider=None: [
                TriageResult(
                    tweet_id=item["id"],
                    score=8.0,
                    categories=["news"],
                    summary="scored",
                    tickers=["NVDA"],
                )
                for item in batch
            ],
        )
        monkeypatch.setattr(triage_mod, "summarize_tweet", lambda *args, **kwargs: "summary")
        monkeypatch.setattr(
            triage_mod,
            "_analyze_media_items",
            lambda media_items, **kwargs: (
                [
                    {
                        **media_items[0],
                        "kind": "chart",
                        "short_description": "chart",
                        "prose_text": "Revenue reaches 100",
                        "prose_summary": "Revenue rises",
                        "chart": {
                            "description": "Revenue trend",
                            "insight": "Revenue reaches 100",
                            "implication": "Momentum improves",
                        },
                    }
                ],
                True,
            ),
        )
        monkeypatch.setattr(
            triage_mod,
            "enrich_tweet",
            lambda **kwargs: EnrichmentResult(
                signal_tier="high_signal",
                insight="insight",
                implications="implications",
                narratives=["ai"],
                tickers=["NVDA"],
            ),
        )
        monkeypatch.setattr(
            triage_mod,
            "summarize_x_article",
            lambda *args, **kwargs: XArticleSummaryResult(
                short_summary="article summary",
                primary_points=[{"point": "Capex rises", "reasoning": "Demand grows", "evidence": "100"}],
                actionable_items=[{"action": "Track capex", "trigger": "Next quarter"}],
            ),
        )

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
            media_min_score=3,
        )

        assert len(results) == 1
        assert conn.write_calls >= 4


def test_enrich_high_signal_parallel_db_access_stays_on_owner_thread(monkeypatch, tmp_path) -> None:
    """Parallel enrichment should only write after futures resolve on the caller thread."""
    db_path = tmp_path / "enrich_owner_thread.db"
    init_db(db_path)

    with get_connection(db_path) as conn:
        inserted = insert_tweet(
            conn,
            tweet_id="main-1",
            author_handle="mainacct",
            content="Main tweet content",
            created_at=_FIXED_TS,
            source="test",
            has_media=True,
            media_items=[{"url": "https://example.com/image.png"}],
        )
        assert inserted is True
        update_tweet_processing(
            conn,
            tweet_id="main-1",
            relevance_score=9.0,
            categories=["news"],
            summary="summary",
            signal_tier="market_relevant",
            tickers=[],
        )
        conn.commit()

    @contextmanager
    def _thread_checked_connection():
        with get_connection(db_path) as raw_conn:
            yield _ThreadCheckingConnection(raw_conn)

    monkeypatch.setattr(pipeline_mod, "get_connection", lambda readonly=False: _thread_checked_connection())
    monkeypatch.setattr(
        pipeline_mod,
        "load_config",
        lambda: {
            "scoring": {"high_signal_threshold": 7},
            "llm": {"max_concurrency_text": 2},
        },
    )
    monkeypatch.setattr(
        triage_mod,
        "_analyze_media_items",
        lambda media_items, **kwargs: (
            [
                {
                    **media_items[0],
                    "kind": "chart",
                    "short_description": "chart",
                    "prose_text": "Revenue reaches 100",
                    "prose_summary": "Revenue rises",
                }
            ],
            True,
        ),
    )
    monkeypatch.setattr(
        pipeline_mod,
        "enrich_tweet",
        lambda **kwargs: EnrichmentResult(
            signal_tier="high_signal",
            insight="insight",
            implications="implications",
            narratives=[],
            tickers=[],
        ),
    )

    results = pipeline_mod.enrich_high_signal(limit=5, enrich_model="dummy-model")

    assert len(results) == 1


def test_expand_links_parallel_db_access_stays_on_owner_thread(monkeypatch, tmp_path) -> None:
    """Parallel link expansion should serialize DB access on the caller thread."""
    db_path = tmp_path / "expand_links_owner_thread.db"
    init_db(db_path)

    with get_connection(db_path) as raw_conn:
        inserted = insert_tweet(
            raw_conn,
            tweet_id="link-1",
            author_handle="root_user",
            content="Interesting thread https://t.co/ext",
            created_at=_FIXED_TS,
            source="test",
            has_link=True,
            links=[{"url": "https://t.co/ext", "expanded_url": "https://t.co/ext"}],
        )
        assert inserted is True
        raw_conn.commit()

        rows = raw_conn.execute("SELECT * FROM tweets WHERE id = ?", ("link-1",)).fetchall()
        conn = _ThreadCheckingConnection(raw_conn)

        monkeypatch.setattr(
            deps_mod,
            "expand_links_in_place",
            lambda _links: [
                {
                    "url": "https://t.co/ext",
                    "expanded_url": "https://github.com/example/project",
                    "display_url": "github.com/example/project",
                }
            ],
        )

        refreshed_rows = deps_mod._expand_links_for_rows(
            conn,
            rows,
            max_workers=4,
            quote_depth=0,
        )

        assert len(refreshed_rows) == 1
        assert conn.write_calls >= 1
        assert refreshed_rows[0]["links_expanded_at"] is not None
