"""Tests for tweet feed API shaping (retweets, display fields, recursive quotes)."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from twag.db import get_connection, insert_tweet, update_tweet_processing
from twag.web.app import create_app


def _insert_processed_tweet(conn, *, tweet_id: str, author_handle: str, content: str, **kwargs) -> None:
    inserted = insert_tweet(
        conn,
        tweet_id=tweet_id,
        author_handle=author_handle,
        content=content,
        created_at=datetime.now(timezone.utc),
        source="test",
        **kwargs,
    )
    assert inserted is True
    update_tweet_processing(
        conn,
        tweet_id=tweet_id,
        relevance_score=7.0,
        categories=["macro"],
        summary=f"summary-{tweet_id}",
        signal_tier="market_relevant",
        tickers=["SPX"],
    )


def test_list_tweets_retweet_display_fields(monkeypatch, tmp_path):
    db_path = tmp_path / "twag_api_retweet.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(
            conn,
            tweet_id="orig-1",
            author_handle="original",
            content="Original author text with context.",
        )
        _insert_processed_tweet(
            conn,
            tweet_id="rt-1",
            author_handle="retweeter",
            content="RT @original: Original author text with context.",
            is_retweet=True,
            retweeted_by_handle="retweeter",
            retweeted_by_name="Retweeter Name",
            original_tweet_id="orig-1",
            original_author_handle="original",
            original_author_name="Original Name",
            original_content="Original author text with context.",
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/api/tweets", params={"sort": "latest", "since": "30d"})
    assert response.status_code == 200
    tweets = response.json()["tweets"]

    rt_tweet = next(t for t in tweets if t["id"] == "rt-1")
    assert rt_tweet["is_retweet"] is True
    assert rt_tweet["retweeted_by_handle"] == "retweeter"
    assert rt_tweet["display_author_handle"] == "original"
    assert rt_tweet["display_tweet_id"] == "orig-1"
    assert rt_tweet["display_content"] == "Original author text with context."


def test_list_tweets_legacy_rt_text_fallback(monkeypatch, tmp_path):
    db_path = tmp_path / "twag_api_legacy_rt.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(
            conn,
            tweet_id="legacy-rt-1",
            author_handle="retweeter",
            content="RT @original: Legacy retweet text that should be attributed correctly.",
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/api/tweets", params={"author": "retweeter", "sort": "latest", "since": "30d"})
    assert response.status_code == 200
    tweets = response.json()["tweets"]
    assert len(tweets) == 1

    rt_tweet = tweets[0]
    assert rt_tweet["is_retweet"] is True
    assert rt_tweet["retweeted_by_handle"] == "retweeter"
    assert rt_tweet["display_author_handle"] == "original"
    assert rt_tweet["display_tweet_id"] == "legacy-rt-1"
    assert rt_tweet["display_content"] == "Legacy retweet text that should be attributed correctly."


def test_list_tweets_decodes_html_entities_in_content_and_display(monkeypatch, tmp_path):
    db_path = tmp_path / "twag_api_html_entities.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(
            conn,
            tweet_id="entity-1",
            author_handle="entity_user",
            content="Spotify is down -33% in a month. A &gt;$100B company with P&amp;L pressure.",
        )
        _insert_processed_tweet(
            conn,
            tweet_id="entity-rt-1",
            author_handle="retweeter",
            content="RT @entity_user: Spotify is down -33% in a month. A &gt;$100B company.",
            is_retweet=True,
            retweeted_by_handle="retweeter",
            original_author_handle="entity_user",
            original_content="Spotify is down -33% in a month. A &gt;$100B company.",
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/api/tweets", params={"sort": "latest", "since": "30d"})
    assert response.status_code == 200
    tweets = response.json()["tweets"]

    base = next(t for t in tweets if t["id"] == "entity-1")
    assert base["content"] == "Spotify is down -33% in a month. A >$100B company with P&L pressure."
    assert base["display_content"] == "Spotify is down -33% in a month. A >$100B company with P&L pressure."

    rt = next(t for t in tweets if t["id"] == "entity-rt-1")
    assert rt["content"] == "RT @entity_user: Spotify is down -33% in a month. A >$100B company."
    assert rt["original_content"] == "Spotify is down -33% in a month. A >$100B company."
    assert rt["display_content"] == "Spotify is down -33% in a month. A >$100B company."


def test_list_tweets_legacy_rt_truncated_text_does_not_override_display_content(monkeypatch, tmp_path):
    db_path = tmp_path / "twag_api_legacy_rt_truncated.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(
            conn,
            tweet_id="legacy-rt-truncated",
            author_handle="retweeter",
            content="RT @original: Legacy retweet text clipped by upstream…",
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/api/tweets", params={"author": "retweeter", "sort": "latest", "since": "30d"})
    assert response.status_code == 200
    tweets = response.json()["tweets"]
    assert len(tweets) == 1

    rt_tweet = tweets[0]
    assert rt_tweet["is_retweet"] is True
    assert rt_tweet["display_author_handle"] == "original"
    # Keep raw display text when fallback text is already truncated.
    assert rt_tweet["display_content"] == "RT @original: Legacy retweet text clipped by upstream…"


def test_list_tweets_builds_recursive_quote_embed(monkeypatch, tmp_path):
    db_path = tmp_path / "twag_api_quotes.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="q3", author_handle="q3_user", content="quote level 3")
        _insert_processed_tweet(
            conn,
            tweet_id="q2",
            author_handle="q2_user",
            content="quote level 2",
            has_quote=True,
            quote_tweet_id="q3",
        )
        _insert_processed_tweet(
            conn,
            tweet_id="q1",
            author_handle="q1_user",
            content="quote level 1",
            has_quote=True,
            quote_tweet_id="q2",
        )
        _insert_processed_tweet(
            conn,
            tweet_id="root",
            author_handle="root_user",
            content="root tweet content",
            has_quote=True,
            quote_tweet_id="q1",
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/api/tweets", params={"author": "root_user", "since": "30d"})
    assert response.status_code == 200
    tweets = response.json()["tweets"]
    assert len(tweets) == 1

    quote_embed = tweets[0]["quote_embed"]
    assert quote_embed["id"] == "q1"
    assert quote_embed["quote_embed"]["id"] == "q2"
    assert quote_embed["quote_embed"]["quote_embed"]["id"] == "q3"


def test_list_tweets_normalizes_self_and_inline_links(monkeypatch, tmp_path):
    db_path = tmp_path / "twag_api_inline_links.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(
            conn,
            tweet_id="2001",
            author_handle="child_user",
            content="child tweet content",
        )
        _insert_processed_tweet(
            conn,
            tweet_id="1001",
            author_handle="root_user",
            content="Password manager with email aliasing https://t.co/self https://t.co/child https://t.co/ext",
            links=[
                {
                    "url": "https://t.co/self",
                    "expanded_url": "https://x.com/root_user/status/1001",
                    "display_url": "x.com/root_user/status/1001",
                },
                {
                    "url": "https://t.co/child",
                    "expanded_url": "https://x.com/child_user/status/2001",
                    "display_url": "x.com/child_user/status/2001",
                },
                {
                    "url": "https://t.co/ext",
                    "expanded_url": "https://github.com/aliasvault/aliasvault",
                    "display_url": "github.com/aliasvault/aliasvault",
                },
            ],
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/api/tweets", params={"author": "root_user", "since": "30d"})
    assert response.status_code == 200
    tweet = response.json()["tweets"][0]

    assert tweet["display_content"] == "Password manager with email aliasing https://github.com/aliasvault/aliasvault"
    assert tweet["quote_embed"]["id"] == "2001"
    assert tweet["inline_quote_embeds"] == []
    assert tweet["external_links"] == [
        {
            "url": "https://github.com/aliasvault/aliasvault",
            "display_url": "github.com/aliasvault/aliasvault",
            "domain": "github.com",
        }
    ]


def test_list_tweets_builds_multiple_inline_quote_embeds(monkeypatch, tmp_path):
    db_path = tmp_path / "twag_api_multiple_inline_links.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="2101", author_handle="child1_user", content="first child")
        _insert_processed_tweet(conn, tweet_id="2202", author_handle="child2_user", content="second child")
        _insert_processed_tweet(
            conn,
            tweet_id="1100",
            author_handle="root2_user",
            content="Context https://t.co/c1 https://t.co/c2",
            links=[
                {
                    "url": "https://t.co/c1",
                    "expanded_url": "https://x.com/child1_user/status/2101",
                    "display_url": "x.com/child1_user/status/2101",
                },
                {
                    "url": "https://t.co/c2",
                    "expanded_url": "https://x.com/child2_user/status/2202",
                    "display_url": "x.com/child2_user/status/2202",
                },
            ],
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/api/tweets", params={"author": "root2_user", "since": "30d"})
    assert response.status_code == 200
    tweet = response.json()["tweets"][0]

    assert tweet["quote_embed"]["id"] == "2101"
    assert [q["id"] for q in tweet["inline_quote_embeds"]] == ["2202"]


def test_list_tweets_drops_unresolved_short_media_link(monkeypatch, tmp_path):
    db_path = tmp_path / "twag_api_media_short_link.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(
            conn,
            tweet_id="3001",
            author_handle="media_user",
            content="Chart update https://t.co/only",
            has_media=True,
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/api/tweets", params={"author": "media_user", "since": "30d"})
    assert response.status_code == 200
    tweet = response.json()["tweets"][0]

    assert tweet["display_content"] == "Chart update"
    assert tweet["external_links"] == []


def test_list_tweets_drops_trailing_unresolved_short_link_when_other_link_resolves(monkeypatch, tmp_path):
    db_path = tmp_path / "twag_api_short_link_mix.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(
            conn,
            tweet_id="3101",
            author_handle="mixed_user",
            content="LLM for voice interactions without ASR stage https://t.co/ext https://t.co/self",
            links=[
                {
                    "url": "https://t.co/ext",
                    "expanded_url": "https://github.com/fixie-ai/ultravox",
                    "display_url": "github.com/fixie-ai/ultravox",
                }
            ],
            has_media=False,
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/api/tweets", params={"author": "mixed_user", "since": "30d"})
    assert response.status_code == 200
    tweet = response.json()["tweets"][0]

    assert (
        tweet["display_content"] == "LLM for voice interactions without ASR stage https://github.com/fixie-ai/ultravox"
    )
    assert tweet["external_links"] == [
        {
            "url": "https://github.com/fixie-ai/ultravox",
            "display_url": "github.com/fixie-ai/ultravox",
            "domain": "github.com",
        }
    ]


def test_list_tweets_does_not_expand_short_urls_on_request(monkeypatch, tmp_path):
    db_path = tmp_path / "twag_api_no_runtime_expansion.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    monkeypatch.setattr("twag.link_utils._expand_short_url", lambda _url: (_ for _ in ()).throw(AssertionError()))
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(
            conn,
            tweet_id="3201",
            author_handle="runtime_user",
            content="No runtime expansion https://t.co/ext",
            links=[
                {
                    "url": "https://t.co/ext",
                    "expanded_url": "https://github.com/example/project",
                    "display_url": "github.com/example/project",
                }
            ],
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/api/tweets", params={"author": "runtime_user", "since": "30d"})
    assert response.status_code == 200
    tweet = response.json()["tweets"][0]
    assert tweet["display_content"] == "No runtime expansion https://github.com/example/project"
