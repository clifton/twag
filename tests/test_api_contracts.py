"""API contract verification tests.

Verifies that:
1. Route responses validate against their declared response_model schemas.
2. GET /reactions/summary and /reactions/export are reachable (not shadowed).
3. GET /tweets/{id} returns the same shape as list endpoint items.
4. Not-found errors return proper HTTP status codes.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from twag.db import get_connection, insert_tweet, update_tweet_processing
from twag.models.api import (
    CategoryListResponse,
    ContextCommandListResponse,
    PromptListResponse,
    ReactionExportResponse,
    ReactionListResponse,
    ReactionSummaryResponse,
    TickerListResponse,
    TweetListResponse,
    TweetResponse,
)
from twag.web.app import create_app


def _setup_app(monkeypatch, tmp_path, db_name="twag_contract.db"):
    db_path = tmp_path / db_name
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()
    return app, db_path


def _insert_processed_tweet(conn, *, tweet_id, author_handle, content, **kwargs):
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


# --- Tweet endpoint contract tests ---


class TestTweetListContract:
    def test_list_tweets_validates_against_response_model(self, monkeypatch, tmp_path):
        app, db_path = _setup_app(monkeypatch, tmp_path)
        with get_connection(db_path) as conn:
            _insert_processed_tweet(conn, tweet_id="t1", author_handle="user1", content="Hello world")
            conn.commit()

        client = TestClient(app)
        resp = client.get("/api/tweets", params={"since": "30d"})
        assert resp.status_code == 200
        # Validates against TweetListResponse schema
        parsed = TweetListResponse.model_validate(resp.json())
        assert parsed.count == 1
        assert parsed.tweets[0].id == "t1"

    def test_list_tweets_items_have_display_fields(self, monkeypatch, tmp_path):
        app, db_path = _setup_app(monkeypatch, tmp_path)
        with get_connection(db_path) as conn:
            _insert_processed_tweet(conn, tweet_id="t2", author_handle="user2", content="Test content")
            conn.commit()

        client = TestClient(app)
        resp = client.get("/api/tweets", params={"since": "30d"})
        tweet = resp.json()["tweets"][0]
        for field in [
            "display_author_handle",
            "display_author_name",
            "display_tweet_id",
            "display_content",
            "quote_embed",
            "inline_quote_embeds",
            "reference_links",
            "external_links",
            "reactions",
        ]:
            assert field in tweet, f"Missing display field: {field}"


class TestSingleTweetContract:
    def test_get_tweet_validates_against_response_model(self, monkeypatch, tmp_path):
        app, db_path = _setup_app(monkeypatch, tmp_path)
        with get_connection(db_path) as conn:
            _insert_processed_tweet(conn, tweet_id="t3", author_handle="user3", content="Single tweet")
            conn.commit()

        client = TestClient(app)
        resp = client.get("/api/tweets/t3")
        assert resp.status_code == 200
        parsed = TweetResponse.model_validate(resp.json())
        assert parsed.id == "t3"

    def test_get_tweet_has_same_shape_as_list_items(self, monkeypatch, tmp_path):
        """GET /tweets/{id} must return the same fields as GET /tweets list items."""
        app, db_path = _setup_app(monkeypatch, tmp_path)
        with get_connection(db_path) as conn:
            _insert_processed_tweet(conn, tweet_id="t4", author_handle="user4", content="Shape test")
            conn.commit()

        client = TestClient(app)
        list_resp = client.get("/api/tweets", params={"since": "30d"})
        single_resp = client.get("/api/tweets/t4")

        list_keys = set(list_resp.json()["tweets"][0].keys())
        single_keys = set(single_resp.json().keys())
        assert list_keys == single_keys, (
            f"Key mismatch: only in list={list_keys - single_keys}, only in single={single_keys - list_keys}"
        )

    def test_get_tweet_no_links_json_field(self, monkeypatch, tmp_path):
        """GET /tweets/{id} must NOT return raw links_json."""
        app, db_path = _setup_app(monkeypatch, tmp_path)
        with get_connection(db_path) as conn:
            _insert_processed_tweet(conn, tweet_id="t5", author_handle="user5", content="No links_json")
            conn.commit()

        client = TestClient(app)
        resp = client.get("/api/tweets/t5")
        assert resp.status_code == 200
        assert "links_json" not in resp.json()

    def test_get_tweet_returns_display_enriched_fields(self, monkeypatch, tmp_path):
        app, db_path = _setup_app(monkeypatch, tmp_path)
        with get_connection(db_path) as conn:
            _insert_processed_tweet(conn, tweet_id="t6", author_handle="user6", content="Display enriched")
            conn.commit()

        client = TestClient(app)
        resp = client.get("/api/tweets/t6")
        data = resp.json()
        assert data["display_author_handle"] == "user6"
        assert data["display_tweet_id"] == "t6"
        assert data["display_content"] == "Display enriched"
        assert isinstance(data["reactions"], list)
        assert isinstance(data["inline_quote_embeds"], list)
        assert isinstance(data["external_links"], list)

    def test_get_tweet_not_found_returns_404(self, monkeypatch, tmp_path):
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.get("/api/tweets/nonexistent")
        assert resp.status_code == 404


# --- Reaction route shadowing tests ---


class TestReactionRouteShadowing:
    def test_reactions_summary_is_reachable(self, monkeypatch, tmp_path):
        """GET /reactions/summary must NOT be shadowed by /reactions/{tweet_id}."""
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.get("/api/reactions/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        # Must NOT be treated as tweet_id="summary"
        assert "tweet_id" not in data

    def test_reactions_export_is_reachable(self, monkeypatch, tmp_path):
        """GET /reactions/export must NOT be shadowed by /reactions/{tweet_id}."""
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.get("/api/reactions/export")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "reactions" in data
        assert "tweet_id" not in data

    def test_reactions_summary_validates_against_model(self, monkeypatch, tmp_path):
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.get("/api/reactions/summary")
        parsed = ReactionSummaryResponse.model_validate(resp.json())
        assert isinstance(parsed.summary, dict)

    def test_reactions_export_validates_against_model(self, monkeypatch, tmp_path):
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.get("/api/reactions/export")
        parsed = ReactionExportResponse.model_validate(resp.json())
        assert parsed.count == 0

    def test_reactions_for_tweet_still_works(self, monkeypatch, tmp_path):
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.get("/api/reactions/some-tweet-id")
        assert resp.status_code == 200
        parsed = ReactionListResponse.model_validate(resp.json())
        assert parsed.tweet_id == "some-tweet-id"


# --- HTTP error code tests ---


class TestHTTPErrorCodes:
    def test_delete_reaction_not_found_returns_404(self, monkeypatch, tmp_path):
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.delete("/api/reactions/99999")
        assert resp.status_code == 404

    def test_invalid_reaction_type_returns_422(self, monkeypatch, tmp_path):
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.post(
            "/api/react",
            json={"tweet_id": "t1", "reaction_type": "invalid"},
        )
        assert resp.status_code == 422

    def test_get_prompt_not_found_returns_404(self, monkeypatch, tmp_path):
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.get("/api/prompts/nonexistent")
        assert resp.status_code == 404

    def test_get_context_command_not_found_returns_404(self, monkeypatch, tmp_path):
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.get("/api/context-commands/nonexistent")
        assert resp.status_code == 404

    def test_delete_context_command_not_found_returns_404(self, monkeypatch, tmp_path):
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.delete("/api/context-commands/nonexistent")
        assert resp.status_code == 404

    def test_rollback_prompt_not_found_returns_404(self, monkeypatch, tmp_path):
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.post("/api/prompts/nonexistent/rollback", params={"version": 1})
        assert resp.status_code == 404


# --- Other endpoint contract tests ---


class TestCategoriesAndTickersContract:
    def test_categories_validates_against_model(self, monkeypatch, tmp_path):
        app, db_path = _setup_app(monkeypatch, tmp_path)
        with get_connection(db_path) as conn:
            _insert_processed_tweet(conn, tweet_id="cat1", author_handle="u1", content="Cat test")
            conn.commit()

        client = TestClient(app)
        resp = client.get("/api/categories")
        assert resp.status_code == 200
        parsed = CategoryListResponse.model_validate(resp.json())
        assert len(parsed.categories) >= 1

    def test_tickers_validates_against_model(self, monkeypatch, tmp_path):
        app, db_path = _setup_app(monkeypatch, tmp_path)
        with get_connection(db_path) as conn:
            _insert_processed_tweet(conn, tweet_id="tick1", author_handle="u1", content="Ticker test")
            conn.commit()

        client = TestClient(app)
        resp = client.get("/api/tickers")
        assert resp.status_code == 200
        parsed = TickerListResponse.model_validate(resp.json())
        assert len(parsed.tickers) >= 1


class TestPromptsContract:
    def test_list_prompts_validates_against_model(self, monkeypatch, tmp_path):
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.get("/api/prompts")
        assert resp.status_code == 200
        parsed = PromptListResponse.model_validate(resp.json())
        assert isinstance(parsed.prompts, list)


class TestContextCommandsContract:
    def test_list_context_commands_validates_against_model(self, monkeypatch, tmp_path):
        app, _ = _setup_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.get("/api/context-commands")
        assert resp.status_code == 200
        parsed = ContextCommandListResponse.model_validate(resp.json())
        assert isinstance(parsed.commands, list)
