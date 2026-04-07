"""Contract tests: single-tweet and list-tweet endpoints return the same field set."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from twag.db import get_connection, insert_tweet, update_tweet_processing
from twag.db.reactions import insert_reaction
from twag.web.app import create_app

_FIXED_TS = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)

# Fields that both /api/tweets and /api/tweets/{id} must return.
SHARED_FIELDS = {
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
    "is_retweet",
    "retweeted_by_handle",
    "retweeted_by_name",
    "original_tweet_id",
    "original_author_handle",
    "original_author_name",
    "original_content",
    "reactions",
    "quote_embed",
    "inline_quote_embeds",
    "reference_links",
    "external_links",
    "display_content",
}


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


# ── Field parity ──────────────────────────────────────────────


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
    tweets = client.get("/api/tweets", params={"since": "9999d"}).json()["tweets"]
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
    listed = client.get("/api/tweets", params={"since": "9999d"}).json()["tweets"][0]
    assert set(single.keys()) == set(listed.keys())


# ── Reactions type ────────────────────────────────────────────


def test_single_tweet_reactions_is_list(monkeypatch, tmp_path):
    """Reactions must be a list of strings, not a string or null."""
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
    """Reactions is an empty list when the tweet has no reactions."""
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
    tweets = client.get("/api/tweets", params={"since": "9999d"}).json()["tweets"]
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
