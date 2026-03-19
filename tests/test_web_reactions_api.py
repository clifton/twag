"""API contract tests for reactions endpoints."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from twag.db import get_connection, insert_reaction, insert_tweet, update_tweet_processing
from twag.web.app import create_app


def _setup_app(monkeypatch, tmp_path, db_name="twag_reactions_test.db"):
    db_path = tmp_path / db_name
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()
    return app, db_path


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


def test_create_reaction_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="t1", author_handle="user1", content="test tweet")
        conn.commit()

    client = TestClient(app)
    resp = client.post("/api/react", json={"tweet_id": "t1", "reaction_type": ">>"})
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["tweet_id"] == "t1"
    assert data["reaction_type"] == ">>"


def test_create_reaction_invalid_type(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="t1", author_handle="user1", content="test")
        conn.commit()

    client = TestClient(app)
    resp = client.post("/api/react", json={"tweet_id": "t1", "reaction_type": "invalid"})
    assert resp.status_code == 200
    assert "error" in resp.json()


def test_get_tweet_reactions_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="t1", author_handle="user1", content="test")
        insert_reaction(conn, "t1", ">>", "important", None)
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/reactions/t1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tweet_id"] == "t1"
    assert isinstance(data["reactions"], list)
    assert len(data["reactions"]) == 1
    r = data["reactions"][0]
    assert "id" in r
    assert r["reaction_type"] == ">>"
    assert r["reason"] == "important"


def test_delete_reaction_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="t1", author_handle="user1", content="test")
        rid = insert_reaction(conn, "t1", ">", None, None)
        conn.commit()

    client = TestClient(app)
    resp = client.delete(f"/api/reactions/{rid}")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Reaction deleted"

    # Deleting again should return error
    resp2 = client.delete(f"/api/reactions/{rid}")
    assert resp2.status_code == 200
    assert "error" in resp2.json()


def test_reactions_summary_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="t1", author_handle="user1", content="test")
        insert_reaction(conn, "t1", ">>", None, None)
        insert_reaction(conn, "t1", ">", None, None)
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/reactions/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert isinstance(data["summary"], dict)


def test_reactions_export_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="t1", author_handle="user1", content="test tweet content")
        insert_reaction(conn, "t1", ">>", "very important", None)
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/reactions/export")
    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data
    assert isinstance(data["reactions"], list)
    if data["count"] > 0:
        item = data["reactions"][0]
        assert "reaction" in item
        assert "tweet" in item
        assert "id" in item["reaction"]
        assert "type" in item["reaction"]
        assert "id" in item["tweet"]
        assert "author" in item["tweet"]


def test_reactions_summary_not_shadowed_by_tweet_id_route(monkeypatch, tmp_path):
    """Verify /reactions/summary is not captured by /reactions/{tweet_id}."""
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="t1", author_handle="user1", content="test")
        insert_reaction(conn, "t1", ">>", None, None)
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/reactions/summary")
    assert resp.status_code == 200
    data = resp.json()
    # Must have "summary" key (from summary endpoint), NOT "tweet_id" (from {tweet_id} endpoint)
    assert "summary" in data
    assert "tweet_id" not in data


def test_reactions_export_not_shadowed_by_tweet_id_route(monkeypatch, tmp_path):
    """Verify /reactions/export is not captured by /reactions/{tweet_id}."""
    app, _ = _setup_app(monkeypatch, tmp_path)
    client = TestClient(app)
    resp = client.get("/api/reactions/export")
    assert resp.status_code == 200
    data = resp.json()
    # Must have "count" key (from export endpoint), NOT "tweet_id" (from {tweet_id} endpoint)
    assert "count" in data
    assert "tweet_id" not in data
