"""Contract tests: API responses match expected shapes and Pydantic models."""

import re
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from twag.db import get_connection, insert_tweet, update_tweet_processing
from twag.db.reactions import insert_reaction
from twag.models.api import TweetResponse
from twag.web.app import create_app

# ISO 8601 pattern (with or without timezone)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

# Fields that both /api/tweets and /api/tweets/{id} must return.
SHARED_FIELDS = set(TweetResponse.model_fields.keys())


def _setup(monkeypatch, tmp_path, db_name="contract.db"):
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
        created_at=datetime.now(timezone.utc),
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


# ── Field parity against TweetResponse model ────────────────


def test_single_tweet_has_all_shared_fields(monkeypatch, tmp_path):
    """The single-tweet endpoint must return every field the list endpoint does."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets/t1").json()
    assert "error" not in body
    missing = SHARED_FIELDS - set(body.keys())
    assert not missing, f"Single-tweet response missing fields: {missing}"


def test_list_tweet_has_all_shared_fields(monkeypatch, tmp_path):
    """The list endpoint must return every shared field."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    tweets = client.get("/api/tweets", params={"since": "30d"}).json()["tweets"]
    assert len(tweets) >= 1
    missing = SHARED_FIELDS - set(tweets[0].keys())
    assert not missing, f"List-tweet response missing fields: {missing}"


def test_field_sets_identical(monkeypatch, tmp_path):
    """Both endpoints return the exact same set of keys for a given tweet."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    single = client.get("/api/tweets/t1").json()
    listed = client.get("/api/tweets", params={"since": "30d"}).json()["tweets"][0]
    assert set(single.keys()) == set(listed.keys())


def test_response_fields_match_pydantic_model(monkeypatch, tmp_path):
    """Both endpoints return exactly the fields defined in TweetResponse."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    single_keys = set(client.get("/api/tweets/t1").json().keys())
    list_keys = set(client.get("/api/tweets", params={"since": "30d"}).json()["tweets"][0].keys())

    model_fields = set(TweetResponse.model_fields.keys())
    assert single_keys == model_fields, (
        f"Single drift: extra={single_keys - model_fields}, missing={model_fields - single_keys}"
    )
    assert list_keys == model_fields, (
        f"List drift: extra={list_keys - model_fields}, missing={model_fields - list_keys}"
    )


# ── Date format consistency ──────────────────────────────────


def test_created_at_iso_format_both_endpoints(monkeypatch, tmp_path):
    """created_at must be ISO 8601 on both endpoints."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    single = client.get("/api/tweets/t1").json()
    listed = client.get("/api/tweets", params={"since": "30d"}).json()["tweets"][0]

    assert single["created_at"] is not None
    assert ISO_DATE_RE.match(single["created_at"]), f"Not ISO: {single['created_at']}"
    assert listed["created_at"] is not None
    assert ISO_DATE_RE.match(listed["created_at"]), f"Not ISO: {listed['created_at']}"


def test_article_processed_at_iso_when_present(monkeypatch, tmp_path):
    """article_processed_at must be ISO 8601 when set, on both endpoints."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        # Simulate article processing by setting article_processed_at
        conn.execute(
            "UPDATE tweets SET article_processed_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), "t1"),
        )
        conn.commit()

    client = TestClient(app)
    single = client.get("/api/tweets/t1").json()
    listed = client.get("/api/tweets", params={"since": "30d"}).json()["tweets"][0]

    assert single["article_processed_at"] is not None
    assert ISO_DATE_RE.match(single["article_processed_at"]), f"Not ISO: {single['article_processed_at']}"
    assert listed["article_processed_at"] is not None
    assert ISO_DATE_RE.match(listed["article_processed_at"]), f"Not ISO: {listed['article_processed_at']}"


# ── Reactions type ────────────────────────────────────────────


def test_single_tweet_reactions_is_list(monkeypatch, tmp_path):
    """reactions must be a list of strings, not a string or null."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        insert_reaction(conn, tweet_id="t1", reaction_type=">>")
        insert_reaction(conn, tweet_id="t1", reaction_type=">")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets/t1").json()
    assert isinstance(body["reactions"], list)
    assert set(body["reactions"]) == {">>", ">"}


def test_single_tweet_reactions_empty_when_none(monkeypatch, tmp_path):
    """reactions is an empty list when the tweet has no reactions."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets/t1").json()
    assert body["reactions"] == []


def test_list_tweet_reactions_is_list(monkeypatch, tmp_path):
    """List endpoint also returns reactions as a list."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        insert_reaction(conn, tweet_id="t1", reaction_type=">>")
        conn.commit()

    client = TestClient(app)
    tweets = client.get("/api/tweets", params={"since": "30d"}).json()["tweets"]
    t = next(tw for tw in tweets if tw["id"] == "t1")
    assert isinstance(t["reactions"], list)
    assert ">>" in t["reactions"]


# ── Enriched display fields ───────────────────────────────────


def test_single_tweet_display_content(monkeypatch, tmp_path):
    """Single-tweet endpoint produces display_content."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn, content="Test &amp; verify")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets/t1").json()
    assert body["display_content"] == "Test & verify"


def test_single_tweet_retweet_display(monkeypatch, tmp_path):
    """Single-tweet endpoint applies retweet display logic."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(
            conn,
            tweet_id="rt-1",
            author_handle="retweeter",
            content="RT @original: The real content",
            is_retweet=True,
            retweeted_by_handle="retweeter",
            retweeted_by_name="RT Name",
            original_tweet_id="orig-1",
            original_author_handle="original",
            original_author_name="Original",
            original_content="The real content",
        )
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets/rt-1").json()
    assert body["display_author_handle"] == "original"
    assert body["display_tweet_id"] == "orig-1"
    assert body["display_content"] == "The real content"


def test_single_tweet_quote_embed(monkeypatch, tmp_path):
    """Single-tweet endpoint resolves quote embeds."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn, tweet_id="quoted", author_handle="quotee", content="I am quoted")
        _insert(
            conn,
            tweet_id="quoter",
            author_handle="quoter_user",
            content="Quoting this",
            has_quote=True,
            quote_tweet_id="quoted",
        )
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets/quoter").json()
    assert body["quote_embed"] is not None
    assert body["quote_embed"]["id"] == "quoted"


def test_single_tweet_external_links(monkeypatch, tmp_path):
    """Single-tweet endpoint returns external_links instead of links_json."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(
            conn,
            content="Check out https://t.co/link1",
            links=[
                {
                    "url": "https://t.co/link1",
                    "expanded_url": "https://example.com/article",
                    "display_url": "example.com/article",
                },
            ],
        )
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets/t1").json()
    assert "links_json" not in body
    assert len(body["external_links"]) == 1
    assert body["external_links"][0]["url"] == "https://example.com/article"


def test_single_tweet_no_links_json(monkeypatch, tmp_path):
    """links_json must not appear in the single-tweet response."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets/t1").json()
    assert "links_json" not in body


# ── Categories endpoint ──────────────────────────────────────


def test_categories_response_shape(monkeypatch, tmp_path):
    """GET /api/categories returns {categories: [{name: str, count: int}]}."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn, tweet_id="t1")
        _insert(conn, tweet_id="t2", author_handle="bob", content="another")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/categories").json()
    assert "categories" in body
    assert isinstance(body["categories"], list)
    for cat in body["categories"]:
        assert "name" in cat and isinstance(cat["name"], str)
        assert "count" in cat and isinstance(cat["count"], int)


def test_categories_returns_aggregated_counts(monkeypatch, tmp_path):
    """Categories endpoint aggregates across tweets."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn, tweet_id="t1")
        _insert(conn, tweet_id="t2", author_handle="bob", content="another")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/categories").json()
    macro = next((c for c in body["categories"] if c["name"] == "macro"), None)
    assert macro is not None
    assert macro["count"] >= 2


# ── Tickers endpoint ─────────────────────────────────────────


def test_tickers_response_shape(monkeypatch, tmp_path):
    """GET /api/tickers returns {tickers: [{symbol: str, count: int}]}."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn, tweet_id="t1")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tickers").json()
    assert "tickers" in body
    assert isinstance(body["tickers"], list)
    for ticker in body["tickers"]:
        assert "symbol" in ticker and isinstance(ticker["symbol"], str)
        assert "count" in ticker and isinstance(ticker["count"], int)


def test_tickers_returns_aggregated_counts(monkeypatch, tmp_path):
    """Tickers endpoint aggregates across tweets."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn, tweet_id="t1")
        _insert(conn, tweet_id="t2", author_handle="bob", content="spx talk")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tickers").json()
    spx = next((t for t in body["tickers"] if t["symbol"] == "SPX"), None)
    assert spx is not None
    assert spx["count"] >= 2


# ── Reactions CRUD endpoints ─────────────────────────────────


def test_react_creates_reaction(monkeypatch, tmp_path):
    """POST /api/react creates a reaction and returns id + tweet_id."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    resp = client.post("/api/react", json={"tweet_id": "t1", "reaction_type": ">>"})
    body = resp.json()
    assert "id" in body
    assert body["tweet_id"] == "t1"
    assert body["reaction_type"] == ">>"


def test_react_invalid_type_returns_error(monkeypatch, tmp_path):
    """POST /api/react with invalid type returns error."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    resp = client.post("/api/react", json={"tweet_id": "t1", "reaction_type": "invalid"})
    body = resp.json()
    assert "error" in body


def test_get_reactions_for_tweet(monkeypatch, tmp_path):
    """GET /api/reactions/{tweet_id} returns reactions list."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        insert_reaction(conn, tweet_id="t1", reaction_type=">>")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/reactions/t1").json()
    assert body["tweet_id"] == "t1"
    assert isinstance(body["reactions"], list)
    assert len(body["reactions"]) >= 1
    r = body["reactions"][0]
    assert "id" in r
    assert "reaction_type" in r


def test_delete_reaction(monkeypatch, tmp_path):
    """DELETE /api/reactions/{id} removes the reaction."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        rid = insert_reaction(conn, tweet_id="t1", reaction_type=">>")
        conn.commit()

    client = TestClient(app)
    resp = client.delete(f"/api/reactions/{rid}")
    assert resp.json()["message"] == "Reaction deleted"


def test_reactions_summary_not_shadowed(monkeypatch, tmp_path):
    """GET /api/reactions/summary is not captured by the {tweet_id} route."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        insert_reaction(conn, tweet_id="t1", reaction_type=">>")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/reactions/summary").json()
    # Must have 'summary' key, NOT 'tweet_id' (which would mean it hit the wrong route)
    assert "summary" in body
    assert "tweet_id" not in body


def test_reactions_export_not_shadowed(monkeypatch, tmp_path):
    """GET /api/reactions/export is not captured by the {tweet_id} route."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        insert_reaction(conn, tweet_id="t1", reaction_type=">>")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/reactions/export").json()
    # Must have 'count' and 'reactions' keys, NOT 'tweet_id'
    assert "count" in body
    assert "reactions" in body
    assert "tweet_id" not in body
