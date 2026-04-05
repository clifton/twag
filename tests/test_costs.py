"""Tests for cost attribution estimation."""

import sqlite3
from datetime import datetime, timezone

from click.testing import CliRunner

from twag.cli import cli
from twag.costs import estimate_costs, total_cost
from twag.db.schema import SCHEMA
from twag.db.tweets import get_cost_attribution_counts


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _insert_tweet(conn, tweet_id, **overrides):
    defaults = {
        "author_handle": "test",
        "content": "test content",
        "created_at": "2026-04-04T12:00:00+00:00",
        "source": "home",
    }
    defaults.update(overrides)
    conn.execute(
        """
        INSERT INTO tweets (id, author_handle, content, created_at, source,
                            processed_at, relevance_score, media_analysis,
                            content_summary, article_processed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tweet_id,
            defaults["author_handle"],
            defaults["content"],
            defaults["created_at"],
            defaults["source"],
            defaults.get("processed_at"),
            defaults.get("relevance_score"),
            defaults.get("media_analysis"),
            defaults.get("content_summary"),
            defaults.get("article_processed_at"),
        ),
    )


class TestEstimateCosts:
    def test_zero_counts(self):
        counts = {
            "tweets_triaged": 0,
            "tweets_enriched": 0,
            "tweets_with_media_analysis": 0,
            "tweets_summarized": 0,
            "articles_processed": 0,
        }
        results = estimate_costs(counts)
        assert all(c.cost_usd == 0.0 for c in results)
        assert total_cost(results) == 0.0

    def test_basic_cost_math(self):
        counts = {
            "tweets_triaged": 100,
            "tweets_enriched": 0,
            "tweets_with_media_analysis": 0,
            "tweets_summarized": 0,
            "articles_processed": 0,
        }
        results = estimate_costs(counts)
        triage = next(c for c in results if c.component == "triage")
        assert triage.call_count == 100
        assert triage.input_tokens == 200_000  # 100 * 2000
        assert triage.output_tokens == 100_000  # 100 * 1000
        assert triage.cost_usd > 0

    def test_all_components(self):
        counts = {
            "tweets_triaged": 10,
            "tweets_enriched": 5,
            "tweets_with_media_analysis": 3,
            "tweets_summarized": 8,
            "articles_processed": 2,
        }
        results = estimate_costs(counts)
        assert len(results) == 5
        assert total_cost(results) > 0

    def test_custom_token_budgets(self):
        counts = {
            "tweets_triaged": 1,
            "tweets_enriched": 0,
            "tweets_with_media_analysis": 0,
            "tweets_summarized": 0,
            "articles_processed": 0,
        }
        custom_budgets = {"triage": (500, 200)}
        results = estimate_costs(counts, token_budgets=custom_budgets)
        triage = next(c for c in results if c.component == "triage")
        assert triage.input_tokens == 500
        assert triage.output_tokens == 200

    def test_custom_model_prices(self):
        counts = {
            "tweets_triaged": 1000,
            "tweets_enriched": 0,
            "tweets_with_media_analysis": 0,
            "tweets_summarized": 0,
            "articles_processed": 0,
        }
        # Very expensive model
        custom_prices = {"gemini-2.5-flash-preview": (1.0, 1.0)}
        results = estimate_costs(counts, model_prices=custom_prices)
        triage = next(c for c in results if c.component == "triage")
        # 1000 calls * 2000 in * $1/1K + 1000 calls * 1000 out * $1/1K = 2000 + 1000 = 3000
        assert triage.cost_usd == 3000.0


class TestGetCostAttributionCounts:
    def test_empty_db(self):
        conn = _make_db()
        counts = get_cost_attribution_counts(conn)
        assert counts["tweets_triaged"] == 0
        assert counts["articles_processed"] == 0

    def test_counts_processed(self):
        conn = _make_db()
        now = datetime.now(timezone.utc).isoformat()
        _insert_tweet(conn, "1", processed_at=now, relevance_score=8.0)
        _insert_tweet(conn, "2", processed_at=now, relevance_score=3.0)
        _insert_tweet(conn, "3")  # unprocessed
        conn.commit()

        counts = get_cost_attribution_counts(conn)
        assert counts["tweets_triaged"] == 2
        assert counts["tweets_enriched"] == 1  # only score >= 7

    def test_counts_media_and_articles(self):
        conn = _make_db()
        now = datetime.now(timezone.utc).isoformat()
        _insert_tweet(conn, "1", media_analysis="chart showing growth")
        _insert_tweet(conn, "2", content_summary="summary text")
        _insert_tweet(conn, "3", article_processed_at=now)
        conn.commit()

        counts = get_cost_attribution_counts(conn)
        assert counts["tweets_with_media_analysis"] == 1
        assert counts["tweets_summarized"] == 1
        assert counts["articles_processed"] == 1

    def test_date_filter(self):
        conn = _make_db()
        now = datetime.now(timezone.utc).isoformat()
        _insert_tweet(conn, "1", processed_at=now, relevance_score=5.0, created_at="2026-04-04T12:00:00+00:00")
        _insert_tweet(conn, "2", processed_at=now, relevance_score=5.0, created_at="2026-04-03T12:00:00+00:00")
        conn.commit()

        counts = get_cost_attribution_counts(conn, date="2026-04-04")
        assert counts["tweets_triaged"] == 1

        counts_all = get_cost_attribution_counts(conn)
        assert counts_all["tweets_triaged"] == 2


class TestCostsCLI:
    def test_smoke(self, monkeypatch, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO tweets (id, author_handle, content, source, processed_at, relevance_score) VALUES (?, ?, ?, ?, ?, ?)",
            ("1", "test", "hello", "home", now, 8.0),
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr("twag.cli.stats.get_connection", lambda readonly=False: sqlite3.connect(str(db_path)))

        # Patch the context manager
        import contextlib

        @contextlib.contextmanager
        def mock_conn(readonly=False):
            c = sqlite3.connect(str(db_path))
            c.row_factory = sqlite3.Row
            try:
                yield c
            finally:
                c.close()

        monkeypatch.setattr("twag.cli.stats.get_connection", mock_conn)

        runner = CliRunner()
        result = runner.invoke(cli, ["costs"])
        assert result.exit_code == 0
        assert "triage" in result.output
        assert "TOTAL" in result.output
