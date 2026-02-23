"""CLI tests for search/browse behavior."""

import json
from contextlib import contextmanager
from datetime import datetime, timezone

from click.testing import CliRunner

from twag.cli import cli
from twag.db.search import FeedTweet, SearchResult


@contextmanager
def _fake_connection(readonly=False):
    yield object()


def _make_search_result(**overrides):
    defaults = dict(
        id="123",
        author_handle="testuser",
        author_name="Test User",
        content="test content",
        summary="test summary",
        created_at=datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc),
        relevance_score=8.5,
        categories=["fed_policy"],
        signal_tier="high",
        tickers=["SPY"],
        bookmarked=False,
        rank=-5.0,
    )
    defaults.update(overrides)
    return SearchResult(**defaults)


def _make_feed_tweet(**overrides):
    defaults = dict(
        id="456",
        author_handle="feeduser",
        author_name="Feed User",
        content="feed content",
        content_summary=None,
        summary="feed summary",
        created_at=datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc),
        relevance_score=9.0,
        categories=["equities"],
        signal_tier="critical",
        tickers=["AAPL"],
        bookmarked=False,
        has_quote=False,
        quote_tweet_id=None,
        has_media=False,
        media_analysis=None,
        media_items=[],
        has_link=False,
        links=[],
        link_summary=None,
        is_x_article=False,
        article_title=None,
        article_preview=None,
        article_text=None,
        article_summary_short=None,
        article_primary_points=[],
        article_action_items=[],
        article_top_visual=None,
        article_processed_at=None,
        is_retweet=False,
        retweeted_by_handle=None,
        retweeted_by_name=None,
        original_tweet_id=None,
        original_author_handle=None,
        original_author_name=None,
        original_content=None,
        reactions=[],
    )
    defaults.update(overrides)
    return FeedTweet(**defaults)


def test_search_with_query_calls_search_tweets(monkeypatch):
    """Search with a query should call search_tweets()."""
    import twag.cli.search as cli_mod

    calls = {}

    def _fake_search_tweets(conn, query, **kwargs):
        calls["query"] = query
        calls["kwargs"] = kwargs
        return [_make_search_result()]

    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "search_tweets", _fake_search_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "inflation"])

    assert result.exit_code == 0
    assert calls["query"] == "inflation"
    assert "@testuser" in result.output


def test_search_without_query_calls_get_feed_tweets(monkeypatch):
    """Search without a query should call get_feed_tweets()."""
    import twag.cli.search as cli_mod

    calls = {}

    def _fake_get_feed_tweets(conn, **kwargs):
        calls["kwargs"] = kwargs
        return [_make_feed_tweet()]

    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_feed_tweets", _fake_get_feed_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["search"])

    assert result.exit_code == 0
    assert "@feeduser" in result.output
    # Default order should be "relevance" (mapped from "score")
    assert calls["kwargs"]["order_by"] == "relevance"


def test_browse_filters_forwarded(monkeypatch):
    """Filters should be forwarded correctly in browse mode."""
    import twag.cli.search as cli_mod

    calls = {}

    def _fake_get_feed_tweets(conn, **kwargs):
        calls["kwargs"] = kwargs
        return [_make_feed_tweet()]

    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_feed_tweets", _fake_get_feed_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "-c", "fed_policy", "-s", "7", "-a", "zerohedge", "-t", "high", "-n", "10"])

    assert result.exit_code == 0
    kw = calls["kwargs"]
    assert kw["category"] == "fed_policy"
    assert kw["min_score"] == 7.0
    assert kw["author"] == "zerohedge"
    assert kw["signal_tier"] == "high"
    assert kw["limit"] == 10


def test_order_rank_without_query_warns(monkeypatch):
    """--order rank without a query should warn and fall back to score."""
    import twag.cli.search as cli_mod

    calls = {}

    def _fake_get_feed_tweets(conn, **kwargs):
        calls["kwargs"] = kwargs
        return [_make_feed_tweet()]

    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_feed_tweets", _fake_get_feed_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "--order", "rank"])

    assert result.exit_code == 0
    assert "Warning" in result.output
    assert "falling back to score" in result.output
    assert calls["kwargs"]["order_by"] == "relevance"


def test_time_parsed_for_browse_mode(monkeypatch):
    """--time should be correctly parsed for browse mode."""
    import twag.cli.search as cli_mod

    calls = {}

    def _fake_get_feed_tweets(conn, **kwargs):
        calls["kwargs"] = kwargs
        return []

    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_feed_tweets", _fake_get_feed_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "--time", "7d"])

    assert result.exit_code == 0
    # since should have been parsed from "7d"
    assert calls["kwargs"]["since"] is not None


def test_default_order_rank_with_query(monkeypatch):
    """Default order should be 'rank' when a query is provided."""
    import twag.cli.search as cli_mod

    calls = {}

    def _fake_search_tweets(conn, query, **kwargs):
        calls["order_by"] = kwargs.get("order_by")
        return []

    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "search_tweets", _fake_search_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "test"])

    assert result.exit_code == 0
    assert calls["order_by"] == "rank"


def test_default_order_score_without_query(monkeypatch):
    """Default order should be 'score' (mapped to 'relevance') without a query."""
    import twag.cli.search as cli_mod

    calls = {}

    def _fake_get_feed_tweets(conn, **kwargs):
        calls["order_by"] = kwargs.get("order_by")
        return []

    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_feed_tweets", _fake_get_feed_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["search"])

    assert result.exit_code == 0
    assert calls["order_by"] == "relevance"


def test_browse_order_time(monkeypatch):
    """--order time without query should map to 'latest'."""
    import twag.cli.search as cli_mod

    calls = {}

    def _fake_get_feed_tweets(conn, **kwargs):
        calls["order_by"] = kwargs.get("order_by")
        return []

    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_feed_tweets", _fake_get_feed_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "--order", "time"])

    assert result.exit_code == 0
    assert calls["order_by"] == "latest"


def test_feed_tweet_to_search_result_conversion():
    """FeedTweet should convert to SearchResult with rank=0.0."""
    from twag.cli.search import _feed_tweet_to_search_result

    ft = _make_feed_tweet()
    sr = _feed_tweet_to_search_result(ft)

    assert sr.id == ft.id
    assert sr.author_handle == ft.author_handle
    assert sr.content == ft.content
    assert sr.summary == ft.summary
    assert sr.relevance_score == ft.relevance_score
    assert sr.categories == ft.categories
    assert sr.tickers == ft.tickers
    assert sr.rank == 0.0


def test_browse_json_includes_feed_fields(monkeypatch):
    """Browse mode JSON should include has_media, has_link, url, and other FeedTweet fields."""
    import twag.cli.search as cli_mod

    def _fake_get_feed_tweets(conn, **kwargs):
        return [_make_feed_tweet(has_media=True, has_link=True)]

    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_feed_tweets", _fake_get_feed_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "-f", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    entry = data[0]
    assert entry["has_media"] is True
    assert entry["has_link"] is True
    assert entry["url"] == "https://x.com/feeduser/status/456"
    assert entry["has_quote"] is False
    assert entry["is_x_article"] is False
    assert entry["is_retweet"] is False
    # Core fields present
    assert entry["relevance_score"] == 9.0
    assert entry["categories"] == ["equities"]


def test_browse_json_includes_media_analysis(monkeypatch):
    """Browse mode JSON should include media_analysis when present."""
    import twag.cli.search as cli_mod

    def _fake_get_feed_tweets(conn, **kwargs):
        return [_make_feed_tweet(has_media=True, media_analysis="Chart shows uptrend")]

    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_feed_tweets", _fake_get_feed_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "-f", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["media_analysis"] == "Chart shows uptrend"


def test_browse_json_omits_absent_optional_fields(monkeypatch):
    """Browse mode JSON should omit optional fields when not present."""
    import twag.cli.search as cli_mod

    def _fake_get_feed_tweets(conn, **kwargs):
        return [_make_feed_tweet()]

    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_feed_tweets", _fake_get_feed_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "-f", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    entry = data[0]
    assert "media_analysis" not in entry
    assert "link_summary" not in entry
    assert "article_summary" not in entry
    assert "retweeted_by" not in entry
    assert "original_author" not in entry


def test_fts_search_json_unchanged(monkeypatch):
    """FTS search JSON should still use SearchResult format (has rank, no has_media)."""
    import twag.cli.search as cli_mod

    def _fake_search_tweets(conn, query, **kwargs):
        return [_make_search_result()]

    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "search_tweets", _fake_search_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "inflation", "-f", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    entry = data[0]
    assert "rank" in entry
    assert "has_media" not in entry
    assert entry["url"] == "https://x.com/testuser/status/123"


def test_browse_json_article_fields(monkeypatch):
    """Browse mode JSON should include article_summary for X Articles."""
    import twag.cli.search as cli_mod

    def _fake_get_feed_tweets(conn, **kwargs):
        return [
            _make_feed_tweet(
                is_x_article=True,
                article_summary_short="Key takeaways from the report",
            )
        ]

    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_feed_tweets", _fake_get_feed_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "-f", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    entry = data[0]
    assert entry["is_x_article"] is True
    assert entry["article_summary"] == "Key takeaways from the report"
