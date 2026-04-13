"""Contract tests: verify API response shapes match frontend TypeScript interfaces."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from twag.db import get_connection, insert_tweet, update_tweet_processing
from twag.db.context_commands import upsert_context_command
from twag.db.prompts import upsert_prompt
from twag.db.reactions import insert_reaction
from twag.web.app import create_app

# ── TypeScript interface field sets ───────────────────────────
# Derived from twag/web/frontend/src/api/types.ts

TS_TWEET_FIELDS = {
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

TS_TWEETS_RESPONSE_FIELDS = {"tweets", "offset", "limit", "count", "has_more"}

TS_QUOTE_EMBED_FIELDS = {"id", "author_handle", "author_name", "content", "created_at"}

TS_EXTERNAL_LINK_FIELDS = {"url", "display_url", "domain"}

TS_REFERENCE_LINK_FIELDS = {"id", "url"}

TS_REACTION_FIELDS = {"id", "reaction_type", "reason", "target", "created_at"}

TS_REACTIONS_RESPONSE_FIELDS = {"tweet_id", "reactions"}

TS_REACTIONS_SUMMARY_FIELDS = {"summary"}

TS_PROMPT_FIELDS = {"id", "name", "template", "version", "updated_at", "updated_by"}

TS_PROMPTS_RESPONSE_FIELDS = {"prompts"}

TS_CONTEXT_COMMAND_FIELDS = {
    "id",
    "name",
    "command_template",
    "description",
    "enabled",
    "created_at",
}

TS_CONTEXT_COMMANDS_RESPONSE_FIELDS = {"commands"}

TS_CATEGORY_FIELDS = {"name", "count"}

TS_CATEGORIES_RESPONSE_FIELDS = {"categories"}

TS_TICKER_FIELDS = {"symbol", "count"}

TS_TICKERS_RESPONSE_FIELDS = {"tickers"}


# ── Helpers ───────────────────────────────────────────────────


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


# ── Tweet field parity ────────────────────────────────────────


def test_single_tweet_has_all_shared_fields(monkeypatch, tmp_path):
    """The single-tweet endpoint must return every field the list endpoint does."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets/t1").json()
    assert "error" not in body
    missing = TS_TWEET_FIELDS - set(body.keys())
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
    missing = TS_TWEET_FIELDS - set(tweets[0].keys())
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


def test_tweets_response_envelope_matches_ts(monkeypatch, tmp_path):
    """TweetsResponse envelope has exactly the TS interface fields."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets", params={"since": "30d"}).json()
    assert set(body.keys()) == TS_TWEETS_RESPONSE_FIELDS


def test_tweet_fields_match_ts_interface(monkeypatch, tmp_path):
    """Tweet object fields are exactly the TS Tweet interface fields."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets/t1").json()
    assert set(body.keys()) == TS_TWEET_FIELDS


# ── Reactions on tweets ───────────────────────────────────────


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
    tweets = client.get("/api/tweets", params={"since": "30d"}).json()["tweets"]
    t = next(tw for tw in tweets if tw["id"] == "t1")
    assert isinstance(t["reactions"], list)
    assert ">>" in t["reactions"]


# ── Enriched display fields ──────────────────────────────────


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


def test_quote_embed_fields_match_ts(monkeypatch, tmp_path):
    """QuoteEmbed shape matches TypeScript QuoteEmbed interface."""
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
    embed = body["quote_embed"]
    assert embed is not None
    assert set(embed.keys()) >= TS_QUOTE_EMBED_FIELDS


def test_external_links_fields_match_ts(monkeypatch, tmp_path):
    """ExternalLink shape matches TypeScript ExternalLink interface."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(
            conn,
            content="Check https://t.co/link1",
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
    link = body["external_links"][0]
    assert set(link.keys()) >= TS_EXTERNAL_LINK_FIELDS


def test_single_tweet_no_links_json(monkeypatch, tmp_path):
    """links_json must not appear in the single-tweet response."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tweets/t1").json()
    assert "links_json" not in body


# ── Reactions endpoints ───────────────────────────────────────


def test_reactions_get_fields_match_ts(monkeypatch, tmp_path):
    """GET /reactions/{tweet_id} matches ReactionsResponse + Reaction interfaces."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        insert_reaction(conn, tweet_id="t1", reaction_type=">>", reason="important")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/reactions/t1").json()
    assert set(body.keys()) == TS_REACTIONS_RESPONSE_FIELDS
    assert len(body["reactions"]) == 1
    assert set(body["reactions"][0].keys()) >= TS_REACTION_FIELDS


def test_reactions_post_returns_id(monkeypatch, tmp_path):
    """POST /react returns an id on success."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    resp = client.post(
        "/api/react",
        json={"tweet_id": "t1", "reaction_type": ">>"},
    )
    body = resp.json()
    assert "id" in body
    assert "error" not in body


def test_reactions_delete(monkeypatch, tmp_path):
    """DELETE /reactions/{id} returns success message."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        rid = insert_reaction(conn, tweet_id="t1", reaction_type=">>")
        conn.commit()

    client = TestClient(app)
    body = client.delete(f"/api/reactions/{rid}").json()
    assert "message" in body


def test_reactions_summary_fields_match_ts(monkeypatch, tmp_path):
    """GET /reactions/summary matches ReactionsSummary interface."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        insert_reaction(conn, tweet_id="t1", reaction_type=">>")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/reactions/summary").json()
    assert set(body.keys()) == TS_REACTIONS_SUMMARY_FIELDS
    assert isinstance(body["summary"], dict)


def test_reactions_summary_not_shadowed(monkeypatch, tmp_path):
    """GET /reactions/summary is NOT intercepted by /reactions/{tweet_id}."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        insert_reaction(conn, tweet_id="t1", reaction_type=">>")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/reactions/summary").json()
    assert "summary" in body
    assert "tweet_id" not in body, "/reactions/summary was shadowed by /reactions/{tweet_id}"


def test_reactions_export_not_shadowed(monkeypatch, tmp_path):
    """GET /reactions/export is NOT intercepted by /reactions/{tweet_id}."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/reactions/export").json()
    assert "count" in body
    assert "tweet_id" not in body, "/reactions/export was shadowed by /reactions/{tweet_id}"


def test_reactions_export_shape(monkeypatch, tmp_path):
    """GET /reactions/export returns count + reactions list."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        insert_reaction(conn, tweet_id="t1", reaction_type=">>")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/reactions/export").json()
    assert "count" in body
    assert "reactions" in body
    assert isinstance(body["reactions"], list)


# ── Prompts endpoints ─────────────────────────────────────────


def test_prompts_list_fields_match_ts(monkeypatch, tmp_path):
    """GET /prompts matches PromptsResponse + Prompt interfaces."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_prompt(conn, "test_prompt", "Score this: {tweet}", "system")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/prompts").json()
    assert set(body.keys()) == TS_PROMPTS_RESPONSE_FIELDS
    assert len(body["prompts"]) >= 1
    prompt = body["prompts"][0]
    assert set(prompt.keys()) >= TS_PROMPT_FIELDS


def test_prompts_get_single_fields_match_ts(monkeypatch, tmp_path):
    """GET /prompts/{name} matches Prompt interface."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_prompt(conn, "scoring", "Score: {tweet}", "system")
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/prompts/scoring").json()
    assert "error" not in body
    assert set(body.keys()) >= TS_PROMPT_FIELDS


def test_prompts_put_returns_version(monkeypatch, tmp_path):
    """PUT /prompts/{name} returns name, version, message."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_prompt(conn, "scoring", "Score: {tweet}", "system")
        conn.commit()

    client = TestClient(app)
    body = client.put(
        "/api/prompts/scoring",
        json={"template": "New template: {tweet}", "updated_by": "test"},
    ).json()
    assert "version" in body
    assert "name" in body


def test_prompts_not_found(monkeypatch, tmp_path):
    """GET /prompts/{name} returns error for missing prompt."""
    _, app = _setup(monkeypatch, tmp_path)
    client = TestClient(app)
    body = client.get("/api/prompts/nonexistent").json()
    assert "error" in body


# ── Context commands endpoints ────────────────────────────────


def test_context_commands_list_fields_match_ts(monkeypatch, tmp_path):
    """GET /context-commands matches ContextCommandsResponse + ContextCommand."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_context_command(conn, "test_cmd", "echo hello", "test command", True)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/context-commands").json()
    assert set(body.keys()) == TS_CONTEXT_COMMANDS_RESPONSE_FIELDS
    assert len(body["commands"]) >= 1
    cmd = body["commands"][0]
    assert set(cmd.keys()) >= TS_CONTEXT_COMMAND_FIELDS


def test_context_commands_get_single_fields_match_ts(monkeypatch, tmp_path):
    """GET /context-commands/{name} matches ContextCommand interface."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_context_command(conn, "test_cmd", "echo hello", "test command", True)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/context-commands/test_cmd").json()
    assert "error" not in body
    assert set(body.keys()) >= TS_CONTEXT_COMMAND_FIELDS


def test_context_commands_post(monkeypatch, tmp_path):
    """POST /context-commands creates a command and returns id + name."""
    _, app = _setup(monkeypatch, tmp_path)
    client = TestClient(app)
    body = client.post(
        "/api/context-commands",
        json={
            "name": "new_cmd",
            "command_template": "echo {tweet_id}",
            "description": "test",
        },
    ).json()
    assert "id" in body
    assert body["name"] == "new_cmd"


def test_context_commands_not_found(monkeypatch, tmp_path):
    """GET /context-commands/{name} returns error for missing command."""
    _, app = _setup(monkeypatch, tmp_path)
    client = TestClient(app)
    body = client.get("/api/context-commands/nonexistent").json()
    assert "error" in body


# ── Health endpoint ───────────────────────────────────────────


def test_health_endpoint(monkeypatch, tmp_path):
    """GET /health returns status, version, uptime_seconds, db_connected."""
    _, app = _setup(monkeypatch, tmp_path)
    client = TestClient(app)
    body = client.get("/api/health").json()
    assert "status" in body
    assert "version" in body
    assert "uptime_seconds" in body
    assert "db_connected" in body
    assert body["status"] in ("ok", "degraded")


# ── Categories endpoint ──────────────────────────────────────


def test_categories_response_matches_ts(monkeypatch, tmp_path):
    """GET /categories matches CategoriesResponse + Category interfaces."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/categories").json()
    assert set(body.keys()) == TS_CATEGORIES_RESPONSE_FIELDS
    assert isinstance(body["categories"], list)
    if body["categories"]:
        cat = body["categories"][0]
        assert set(cat.keys()) >= TS_CATEGORY_FIELDS


# ── Tickers endpoint ─────────────────────────────────────────


def test_tickers_response_matches_ts(monkeypatch, tmp_path):
    """GET /tickers matches TickersResponse + Ticker interfaces."""
    db_path, app = _setup(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert(conn)
        conn.commit()

    client = TestClient(app)
    body = client.get("/api/tickers").json()
    assert set(body.keys()) == TS_TICKERS_RESPONSE_FIELDS
    assert isinstance(body["tickers"], list)
    if body["tickers"]:
        ticker = body["tickers"][0]
        assert set(ticker.keys()) >= TS_TICKER_FIELDS
