"""Backward-compatibility guards for the public web API response shape.

Pins the documented field set for ``GET /api/tweets`` and
``GET /api/tweets/{id}`` so that future refactors can't silently drop fields
that callers (frontend, agent integrations) depend on.

The complementary contract test in ``test_api_contracts.py`` asserts list and
single-tweet endpoints expose the *same* field set. This file adds two
backward-compat-specific guarantees:

1. Every field documented in CLAUDE.md (``display_content``, ``quote_embed``,
   ``inline_quote_embeds``, ``external_links``) must be present on both
   endpoints.
2. A core minimum set of historically-present fields cannot regress.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from twag.db import get_connection, insert_tweet, update_tweet_processing
from twag.web.app import create_app

_FIXED_TS = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)


# Fields explicitly documented in CLAUDE.md as part of the web feed surface.
# Removing any of these is a breaking change for the documented contract.
DOCUMENTED_DISPLAY_FIELDS = {
    "display_content",
    "quote_embed",
    "inline_quote_embeds",
    "external_links",
}


# Historical core field set — these have shipped for a long time and removing
# any of them silently would break agent/automation consumers.
CORE_TWEET_FIELDS = {
    "id",
    "author_handle",
    "content",
    "created_at",
    "relevance_score",
    "categories",
    "summary",
    "signal_tier",
    "tickers",
    "bookmarked",
    "is_retweet",
    "reactions",
}


def _setup(monkeypatch, tmp_path, db_name="bc_api.db"):
    db_path = tmp_path / db_name
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()
    return db_path, app


def _insert(conn, tweet_id="t1", author_handle="alice", content="hello world", **kw):
    assert insert_tweet(
        conn,
        tweet_id=tweet_id,
        author_handle=author_handle,
        content=content,
        created_at=_FIXED_TS,
        source="test",
        **kw,
    )
    update_tweet_processing(
        conn,
        tweet_id=tweet_id,
        relevance_score=7.0,
        categories=["macro"],
        summary=f"summary-{tweet_id}",
        signal_tier="market_relevant",
        tickers=["SPX"],
    )


def test_documented_display_fields_on_single_tweet(monkeypatch, tmp_path):
    """CLAUDE.md guarantees these fields on the single-tweet endpoint."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets/t1").json()
    missing = DOCUMENTED_DISPLAY_FIELDS - set(body.keys())
    assert not missing, (
        f"Single-tweet response is missing fields documented in CLAUDE.md: {missing}. "
        "Update CLAUDE.md or restore the field — do not silently drop."
    )


def test_documented_display_fields_on_list(monkeypatch, tmp_path):
    """CLAUDE.md guarantees these fields on the list endpoint too."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    tweets = client.get("/api/tweets", params={"since": "9999d"}).json()["tweets"]
    assert len(tweets) >= 1
    missing = DOCUMENTED_DISPLAY_FIELDS - set(tweets[0].keys())
    assert not missing, f"List-tweet response is missing CLAUDE.md fields: {missing}"


def test_core_fields_on_single_tweet(monkeypatch, tmp_path):
    """Long-standing core fields cannot be removed without breaking integrations."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets/t1").json()
    missing = CORE_TWEET_FIELDS - set(body.keys())
    assert not missing, f"Single-tweet response dropped core fields: {missing}"


def test_core_fields_on_list(monkeypatch, tmp_path):
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    tweets = client.get("/api/tweets", params={"since": "9999d"}).json()["tweets"]
    missing = CORE_TWEET_FIELDS - set(tweets[0].keys())
    assert not missing, f"List response dropped core fields: {missing}"


def test_external_links_replaces_links_json(monkeypatch, tmp_path):
    """The API exposes ``external_links``, not the raw ``links_json`` storage column."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(
            conn,
            content="See https://t.co/abc",
            links=[
                {
                    "url": "https://t.co/abc",
                    "expanded_url": "https://example.com/article",
                    "display_url": "example.com/article",
                },
            ],
        )
        conn.commit()

    client = TestClient(app)
    single = client.get("/api/tweets/t1").json()
    assert "external_links" in single
    assert "links_json" not in single, "links_json is an internal column; never expose it"

    listed = client.get("/api/tweets", params={"since": "9999d"}).json()["tweets"][0]
    assert "external_links" in listed
    assert "links_json" not in listed


def test_response_is_json_object_with_tweets_key(monkeypatch, tmp_path):
    """The list endpoint shape ``{"tweets": [...]}`` must not change."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets", params={"since": "9999d"}).json()
    assert isinstance(body, dict)
    assert "tweets" in body
    assert isinstance(body["tweets"], list)
