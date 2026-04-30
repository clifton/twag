"""Contract tests: API responses match the frontend TypeScript types in
``twag/web/frontend/src/api/types.ts``.

These tests assert the *shape* of responses (which keys are present, which
types they hold) for the endpoints the frontend depends on. They are not full
behavioural tests — they exist to catch silent contract drift between the
FastAPI backend and the React client (e.g. a renamed field or a route that
gets shadowed by a parameterized one).
"""

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


# ── Reactions endpoints ──────────────────────────────────────
# Static-suffix routes (/reactions/summary, /reactions/export) must be
# declared before /reactions/{tweet_id} or they get shadowed.


def test_reactions_summary_not_shadowed(monkeypatch, tmp_path):
    """GET /api/reactions/summary returns {summary: {...}}, not the {tweet_id, reactions} shape."""
    _, app = _setup(monkeypatch, tmp_path)
    body = TestClient(app).get("/api/reactions/summary").json()
    assert "summary" in body, f"Expected summary key; got {sorted(body)}"
    assert isinstance(body["summary"], dict)
    # If shadowed by /{tweet_id}, body would have tweet_id="summary" — guard against regression.
    assert "tweet_id" not in body


def test_reactions_export_not_shadowed(monkeypatch, tmp_path):
    """GET /api/reactions/export returns {count, reactions: [...]}, not the per-tweet shape."""
    _, app = _setup(monkeypatch, tmp_path)
    body = TestClient(app).get("/api/reactions/export").json()
    assert set(body) >= {"count", "reactions"}, f"Got {sorted(body)}"
    assert isinstance(body["reactions"], list)
    assert isinstance(body["count"], int)


def test_reactions_for_tweet_shape(monkeypatch, tmp_path):
    """GET /api/reactions/{tweet_id} returns Reaction[] matching the TS interface."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        insert_reaction(conn, tweet_id="t1", reaction_type=">>", reason="great point")
        conn.commit()

    body = TestClient(app).get("/api/reactions/t1").json()
    assert body["tweet_id"] == "t1"
    assert isinstance(body["reactions"], list) and body["reactions"]
    expected = {"id", "reaction_type", "reason", "target", "created_at"}
    missing = expected - set(body["reactions"][0])
    assert not missing, f"Reaction missing keys: {missing}"


def test_create_reaction_returns_id(monkeypatch, tmp_path):
    """POST /api/react returns either {id, tweet_id, reaction_type} or {id, message}."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    body = (
        TestClient(app)
        .post(
            "/api/react",
            json={"tweet_id": "t1", "reaction_type": ">"},
        )
        .json()
    )
    assert "id" in body
    # Non-mute path includes tweet_id and reaction_type
    assert body["tweet_id"] == "t1"
    assert body["reaction_type"] == ">"


# ── Prompt endpoints ─────────────────────────────────────────


def test_prompts_list_shape(monkeypatch, tmp_path):
    """GET /api/prompts returns {prompts: Prompt[]} matching the TS interface."""
    _, app = _setup(monkeypatch, tmp_path)
    body = TestClient(app).get("/api/prompts").json()
    assert "prompts" in body and isinstance(body["prompts"], list)
    assert body["prompts"], "Default prompts should be seeded"
    expected = {"id", "name", "template", "version", "updated_at", "updated_by"}
    missing = expected - set(body["prompts"][0])
    assert not missing, f"Prompt missing keys: {missing}"


def test_prompt_history_shape(monkeypatch, tmp_path):
    """GET /api/prompts/{name}/history returns entries with updated_at + updated_by.

    Frontend ``PromptHistoryEntry`` requires both fields; the history table
    only persists ``created_at`` so the route must alias it to ``updated_at``
    and surface the prompts row's ``updated_by`` at the time of archival.
    """
    _, app = _setup(monkeypatch, tmp_path)
    client = TestClient(app)

    # Seed history by updating an existing prompt twice.
    client.put("/api/prompts/triage", json={"template": "v2", "updated_by": "alice"})
    client.put("/api/prompts/triage", json={"template": "v3", "updated_by": "bob"})

    body = client.get("/api/prompts/triage/history").json()
    assert body["name"] == "triage"
    assert isinstance(body["history"], list) and len(body["history"]) >= 2
    expected = {"version", "template", "updated_at", "updated_by"}
    for entry in body["history"]:
        missing = expected - set(entry)
        assert not missing, f"PromptHistoryEntry missing keys: {missing} got={sorted(entry)}"
        # updated_at must be ISO 8601 ("T" separator) so JS new Date() parses reliably.
        assert "T" in entry["updated_at"], f"Non-ISO timestamp: {entry['updated_at']!r}"


def test_get_prompt_shape(monkeypatch, tmp_path):
    """GET /api/prompts/{name} returns the Prompt shape."""
    _, app = _setup(monkeypatch, tmp_path)
    body = TestClient(app).get("/api/prompts/triage").json()
    expected = {"id", "name", "template", "version", "updated_at", "updated_by"}
    missing = expected - set(body)
    assert not missing, f"Prompt response missing keys: {missing}"


# ── Context-command endpoints ────────────────────────────────


def test_context_commands_list_shape(monkeypatch, tmp_path):
    """GET /api/context-commands returns {commands: ContextCommand[]}."""
    _, app = _setup(monkeypatch, tmp_path)
    body = TestClient(app).get("/api/context-commands").json()
    assert "commands" in body and isinstance(body["commands"], list)


def test_context_command_create_and_fetch(monkeypatch, tmp_path):
    """POST + GET /api/context-commands/{name} return the ContextCommand shape."""
    _, app = _setup(monkeypatch, tmp_path)
    client = TestClient(app)
    client.post(
        "/api/context-commands",
        json={
            "name": "ticker_grep",
            "command_template": "grep {ticker} /tmp/foo",
            "description": "demo",
            "enabled": True,
        },
    )
    body = client.get("/api/context-commands/ticker_grep").json()
    expected = {"id", "name", "command_template", "description", "enabled", "created_at"}
    missing = expected - set(body)
    assert not missing, f"ContextCommand missing keys: {missing}"


# ── Feed filters ─────────────────────────────────────────────


def test_feed_accepts_all_filter_query_params(monkeypatch, tmp_path):
    """The TS FeedFilters keys (since/min_score/signal_tier/category/ticker/author/bookmarked/sort)
    are all accepted by GET /api/tweets without raising 422."""
    _, app = _setup(monkeypatch, tmp_path)
    r = TestClient(app).get(
        "/api/tweets",
        params={
            "since": "today",
            "min_score": 5,
            "signal_tier": "high_signal",
            "category": "fed_policy",
            "ticker": "SPX",
            "author": "alice",
            "bookmarked": "true",
            "sort": "latest",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"tweets", "offset", "limit", "count", "has_more"} <= set(body)
