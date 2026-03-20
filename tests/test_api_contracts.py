"""API contract verification tests.

Ensures that backend route responses match the declared Pydantic models
and that frontend TypeScript types stay aligned with backend field names.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from twag.db import get_connection, insert_tweet, update_tweet_processing
from twag.models.api import CategoryCount, TickerCount, TweetListResponse, TweetResponse
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


# -- Expected field sets derived from Pydantic models --

TWEET_RESPONSE_FIELDS = set(TweetResponse.model_fields.keys())

TWEET_LIST_RESPONSE_FIELDS = set(TweetListResponse.model_fields.keys())


# ---------------------------------------------------------------------------
# /api/tweets list endpoint
# ---------------------------------------------------------------------------


def test_list_tweets_response_validates_against_pydantic_model(monkeypatch, tmp_path):
    """Every field in /api/tweets response must parse via TweetListResponse."""
    db_path = tmp_path / "contract_list.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="c-1", author_handle="alice", content="Contract test tweet")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/tweets", params={"since": "30d"})
    assert resp.status_code == 200

    # Must validate without errors
    parsed = TweetListResponse.model_validate(resp.json())
    assert parsed.count == 1
    assert parsed.tweets[0].id == "c-1"


def test_list_tweets_response_keys_match_model_fields(monkeypatch, tmp_path):
    """JSON keys in each tweet must exactly match TweetResponse field names."""
    db_path = tmp_path / "contract_keys.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="c-2", author_handle="bob", content="Key check")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/tweets", params={"since": "30d"})
    tweet_keys = set(resp.json()["tweets"][0].keys())
    assert tweet_keys == TWEET_RESPONSE_FIELDS


def test_list_tweets_reactions_is_list(monkeypatch, tmp_path):
    """reactions field must be a list of strings, not string|null."""
    db_path = tmp_path / "contract_reactions.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="c-3", author_handle="carol", content="Reactions check")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/tweets", params={"since": "30d"})
    tweet = resp.json()["tweets"][0]
    assert isinstance(tweet["reactions"], list)


# ---------------------------------------------------------------------------
# /api/tweets/{tweet_id} single endpoint
# ---------------------------------------------------------------------------


def test_single_tweet_response_validates_against_pydantic_model(monkeypatch, tmp_path):
    """Single tweet endpoint must validate against TweetResponse."""
    db_path = tmp_path / "contract_single.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="s-1", author_handle="dave", content="Single tweet test")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/tweets/s-1")
    assert resp.status_code == 200
    data = resp.json()
    assert "error" not in data

    parsed = TweetResponse.model_validate(data)
    assert parsed.id == "s-1"


def test_single_tweet_keys_match_list_tweet_keys(monkeypatch, tmp_path):
    """Single tweet endpoint must return the same field set as the list endpoint."""
    db_path = tmp_path / "contract_single_keys.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="sk-1", author_handle="eve", content="Field alignment")
        conn.commit()

    client = TestClient(app)

    list_resp = client.get("/api/tweets", params={"since": "30d"})
    list_keys = set(list_resp.json()["tweets"][0].keys())

    single_resp = client.get("/api/tweets/sk-1")
    single_keys = set(single_resp.json().keys())

    assert single_keys == list_keys, f"Missing: {list_keys - single_keys}, Extra: {single_keys - list_keys}"


def test_single_tweet_has_enriched_display_fields(monkeypatch, tmp_path):
    """Single tweet must include display_content, quote_embed, external_links, etc."""
    db_path = tmp_path / "contract_enriched.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="e-1", author_handle="frank", content="Enriched fields check")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/tweets/e-1")
    data = resp.json()

    enriched_fields = {
        "display_author_handle",
        "display_author_name",
        "display_tweet_id",
        "display_content",
        "quote_embed",
        "inline_quote_embeds",
        "reference_links",
        "external_links",
    }
    assert enriched_fields.issubset(set(data.keys()))


def test_single_tweet_no_links_json(monkeypatch, tmp_path):
    """Single tweet must NOT expose raw links_json (replaced by external_links)."""
    db_path = tmp_path / "contract_no_links_json.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="nlj-1", author_handle="grace", content="No links_json")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/tweets/nlj-1")
    assert "links_json" not in resp.json()


def test_single_tweet_reactions_is_list(monkeypatch, tmp_path):
    """Single tweet reactions must be list[str]."""
    db_path = tmp_path / "contract_single_reactions.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="sr-1", author_handle="heidi", content="Reactions type")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/tweets/sr-1")
    assert isinstance(resp.json()["reactions"], list)


# ---------------------------------------------------------------------------
# /api/categories
# ---------------------------------------------------------------------------


def test_categories_response_shape(monkeypatch, tmp_path):
    """Categories endpoint must return {categories: [{name, count}]}."""
    db_path = tmp_path / "contract_cats.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="cat-1", author_handle="ivan", content="Cat test")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert "categories" in data
    for cat in data["categories"]:
        parsed = CategoryCount.model_validate(cat)
        assert parsed.count > 0


# ---------------------------------------------------------------------------
# /api/tickers
# ---------------------------------------------------------------------------


def test_tickers_response_shape(monkeypatch, tmp_path):
    """Tickers endpoint must return {tickers: [{symbol, count}]}."""
    db_path = tmp_path / "contract_tickers.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="tick-1", author_handle="judy", content="Ticker test")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/tickers")
    assert resp.status_code == 200
    data = resp.json()
    assert "tickers" in data
    for ticker in data["tickers"]:
        parsed = TickerCount.model_validate(ticker)
        assert parsed.count > 0


# ---------------------------------------------------------------------------
# Frontend TypeScript alignment
# ---------------------------------------------------------------------------

# Fields that the frontend Tweet interface expects from the backend.
# Extracted from twag/web/frontend/src/api/types.ts Tweet interface.
FRONTEND_TWEET_FIELDS = {
    "id",
    "author_handle",
    "author_name",
    "display_author_handle",
    "display_author_name",
    "display_tweet_id",
    "content",
    "content_summary",
    "summary",
    "created_at",
    "relevance_score",
    "categories",
    "signal_tier",
    "tickers",
    "bookmarked",
    "has_quote",
    "quote_tweet_id",
    "has_media",
    "media_analysis",
    "media_items",
    "has_link",
    "link_summary",
    "is_x_article",
    "article_title",
    "article_preview",
    "article_text",
    "article_summary_short",
    "article_primary_points",
    "article_action_items",
    "article_top_visual",
    "article_processed_at",
    "reactions",
    "is_retweet",
    "retweeted_by_handle",
    "retweeted_by_name",
    "original_tweet_id",
    "original_author_handle",
    "original_author_name",
    "original_content",
    "quote_embed",
    "inline_quote_embeds",
    "reference_links",
    "external_links",
    "display_content",
}


def test_frontend_tweet_fields_match_backend_model():
    """Frontend TypeScript Tweet interface fields must match TweetResponse model fields."""
    assert FRONTEND_TWEET_FIELDS == TWEET_RESPONSE_FIELDS, (
        f"Frontend-only: {FRONTEND_TWEET_FIELDS - TWEET_RESPONSE_FIELDS}, "
        f"Backend-only: {TWEET_RESPONSE_FIELDS - FRONTEND_TWEET_FIELDS}"
    )


def test_frontend_tweet_fields_match_list_api_response(monkeypatch, tmp_path):
    """Frontend fields must match actual API response keys (not just model)."""
    db_path = tmp_path / "contract_frontend_api.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="fe-1", author_handle="karl", content="Frontend alignment")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/tweets", params={"since": "30d"})
    api_keys = set(resp.json()["tweets"][0].keys())
    assert api_keys == FRONTEND_TWEET_FIELDS, (
        f"Frontend-only: {FRONTEND_TWEET_FIELDS - api_keys}, API-only: {api_keys - FRONTEND_TWEET_FIELDS}"
    )
