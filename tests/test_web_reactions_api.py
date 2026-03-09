"""Tests for reactions API routes."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from twag.db import get_connection, insert_reaction, insert_tweet, update_tweet_processing
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


def test_create_reaction(monkeypatch, tmp_path):
    db_path = tmp_path / "reactions_create.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="r-1", author_handle="user1", content="Test tweet")
        conn.commit()

    client = TestClient(app)
    resp = client.post("/api/react", json={"tweet_id": "r-1", "reaction_type": ">>"})
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["tweet_id"] == "r-1"
    assert data["reaction_type"] == ">>"


def test_get_tweet_reactions(monkeypatch, tmp_path):
    db_path = tmp_path / "reactions_get.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="r-2", author_handle="user1", content="Test tweet")
        insert_reaction(conn, "r-2", ">>", reason="important")
        insert_reaction(conn, "r-2", ">")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/reactions/r-2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tweet_id"] == "r-2"
    assert len(data["reactions"]) == 2


def test_delete_reaction(monkeypatch, tmp_path):
    db_path = tmp_path / "reactions_delete.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="r-3", author_handle="user1", content="Test tweet")
        rid = insert_reaction(conn, "r-3", ">>")
        conn.commit()

    client = TestClient(app)
    resp = client.delete(f"/api/reactions/{rid}")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Reaction deleted"


def test_reactions_summary(monkeypatch, tmp_path):
    db_path = tmp_path / "reactions_summary.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="r-4", author_handle="user1", content="Test tweet")
        insert_reaction(conn, "r-4", ">>")
        insert_reaction(conn, "r-4", ">>")
        insert_reaction(conn, "r-4", ">")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/reactions/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"][">>"] == 2
    assert data["summary"][">"] == 1


def test_reactions_export(monkeypatch, tmp_path):
    db_path = tmp_path / "reactions_export.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        _insert_processed_tweet(conn, tweet_id="r-5", author_handle="user1", content="Test tweet for export")
        insert_reaction(conn, "r-5", ">>", reason="good insight")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/reactions/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["reactions"][0]["reaction"]["type"] == ">>"
    assert data["reactions"][0]["tweet"]["id"] == "r-5"


def test_summary_not_shadowed_by_tweet_id_route(monkeypatch, tmp_path):
    """Verify /reactions/summary is not intercepted by /reactions/{tweet_id}."""
    db_path = tmp_path / "reactions_shadow.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    # Don't insert any tweet with id "summary"
    client = TestClient(app)
    resp = client.get("/api/reactions/summary")
    assert resp.status_code == 200
    # Should return summary format, not tweet_id format
    data = resp.json()
    assert "summary" in data
    assert "tweet_id" not in data


def test_export_not_shadowed_by_tweet_id_route(monkeypatch, tmp_path):
    """Verify /reactions/export is not intercepted by /reactions/{tweet_id}."""
    db_path = tmp_path / "reactions_shadow2.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    client = TestClient(app)
    resp = client.get("/api/reactions/export")
    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data
    assert "tweet_id" not in data
