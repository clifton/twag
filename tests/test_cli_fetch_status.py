"""CLI tests for single-status fetch behavior."""

from click.testing import CliRunner

from twag.cli import cli
from twag.fetcher import Tweet


def _sample_tweet() -> Tweet:
    return Tweet(
        id="2019488673935552978",
        author_handle="undrvalue",
        author_name="market participant",
        content="Google's $180 Billion Bet",
        created_at=None,
        has_quote=False,
        quote_tweet_id=None,
        has_media=False,
        media_items=[],
        has_link=True,
        is_x_article=True,
        article_title="Google's $180 Billion Bet: Is This the Top?",
        article_preview="Preview",
        article_text="Long article body",
        is_retweet=False,
        retweeted_by_handle=None,
        retweeted_by_name=None,
        original_tweet_id=None,
        original_author_handle=None,
        original_author_name=None,
        original_content=None,
        raw={},
    )


def test_fetch_status_id_fast_path(monkeypatch):
    """`twag fetch <status>` should fetch/store only that status."""
    import twag.cli as cli_mod
    import twag.fetcher as fetcher_mod
    import twag.processor as processor_mod

    calls: dict[str, object] = {}

    def _forbidden(*args, **kwargs):
        raise AssertionError("timeline/bookmark fetch path should not run for single-status fetch")

    def _fake_store_fetched_tweets(
        tweets,
        source,
        query_params=None,
        status_cb=None,
        progress_cb=None,
        total_cb=None,
    ):
        calls["tweets"] = tweets
        calls["source"] = source
        calls["query_params"] = query_params
        if status_cb:
            status_cb("Storing status")
        if progress_cb:
            progress_cb(1)
        return 1, 1

    monkeypatch.setattr(cli_mod, "init_db", lambda: None)
    monkeypatch.setattr(fetcher_mod, "read_tweet", lambda _id: _sample_tweet())
    monkeypatch.setattr(fetcher_mod, "fetch_home_timeline", _forbidden)
    monkeypatch.setattr(fetcher_mod, "fetch_user_tweets", _forbidden)
    monkeypatch.setattr(fetcher_mod, "fetch_search", _forbidden)
    monkeypatch.setattr(fetcher_mod, "fetch_bookmarks", _forbidden)
    monkeypatch.setattr(processor_mod, "store_fetched_tweets", _fake_store_fetched_tweets)

    runner = CliRunner()
    result = runner.invoke(cli, ["fetch", "2019488673935552978"])

    assert result.exit_code == 0
    assert "Fetching status 2019488673935552978..." in result.output
    assert "Fetched 1 tweets, 1 new" in result.output
    assert calls["source"] == "status"
    assert calls["query_params"] == {"status_id_or_url": "2019488673935552978"}
    assert isinstance(calls["tweets"], list)
    assert len(calls["tweets"]) == 1


def test_fetch_status_id_not_found(monkeypatch):
    """Single-status fetch should fail clearly when status cannot be read."""
    import twag.cli as cli_mod
    import twag.fetcher as fetcher_mod

    monkeypatch.setattr(cli_mod, "init_db", lambda: None)
    monkeypatch.setattr(fetcher_mod, "read_tweet", lambda _id: None)

    runner = CliRunner()
    result = runner.invoke(cli, ["fetch", "999"])

    assert result.exit_code == 1
    assert "Status not found or unreadable: 999" in result.output
