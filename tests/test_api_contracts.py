"""Contract verification tests: validate API response shapes against Pydantic models."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from twag.db import get_connection, insert_tweet, update_tweet_processing
from twag.models.api import TweetListResponse, TweetResponse
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


def test_list_tweets_matches_tweet_list_response_model(monkeypatch, tmp_path):
    """GET /tweets response validates against TweetListResponse."""
    db_path = tmp_path / "contract_list.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="c-1", author_handle="user1", content="Contract test tweet")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/tweets", params={"since": "30d"})
    assert resp.status_code == 200

    # Validate the full response against Pydantic model
    validated = TweetListResponse.model_validate(resp.json())
    assert validated.count == 1
    assert validated.tweets[0].id == "c-1"


def test_get_tweet_matches_tweet_response_model(monkeypatch, tmp_path):
    """GET /tweets/{id} response validates against TweetResponse."""
    db_path = tmp_path / "contract_get.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="c-2", author_handle="user2", content="Single tweet test")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/tweets/c-2")
    assert resp.status_code == 200

    data = resp.json()
    assert "error" not in data
    validated = TweetResponse.model_validate(data)
    assert validated.id == "c-2"
    assert validated.display_author_handle == "user2"
    assert validated.display_content is not None


def test_get_tweet_has_enriched_fields(monkeypatch, tmp_path):
    """GET /tweets/{id} returns the same enriched fields as list_tweets."""
    db_path = tmp_path / "contract_enriched.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="e-1", author_handle="enriched_user", content="Enriched tweet")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/tweets/e-1")
    assert resp.status_code == 200
    data = resp.json()

    # These enriched fields must be present (not just in list_tweets)
    enriched_fields = [
        "display_content",
        "display_author_handle",
        "display_author_name",
        "display_tweet_id",
        "quote_embed",
        "inline_quote_embeds",
        "reference_links",
        "external_links",
        "reactions",
    ]
    for field in enriched_fields:
        assert field in data, f"Missing enriched field: {field}"

    # reactions should be a list, not a string
    assert isinstance(data["reactions"], list)

    # links_json should NOT be present (raw DB field)
    assert "links_json" not in data


def test_list_tweets_and_get_tweet_share_field_set(monkeypatch, tmp_path):
    """list_tweets and get_tweet return the same set of fields."""
    db_path = tmp_path / "contract_fields.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="f-1", author_handle="field_user", content="Field check")
        conn.commit()

    client = TestClient(app)

    list_resp = client.get("/api/tweets", params={"since": "30d"})
    assert list_resp.status_code == 200
    list_fields = set(list_resp.json()["tweets"][0].keys())

    get_resp = client.get("/api/tweets/f-1")
    assert get_resp.status_code == 200
    get_fields = set(get_resp.json().keys())

    assert list_fields == get_fields, (
        f"Field mismatch: list-only={list_fields - get_fields}, get-only={get_fields - list_fields}"
    )
