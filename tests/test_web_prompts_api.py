"""Tests for prompts API routes."""

from fastapi.testclient import TestClient

from twag.db import get_connection, seed_prompts
from twag.web.app import create_app


def test_list_prompts(monkeypatch, tmp_path):
    db_path = tmp_path / "prompts_list.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        seed_prompts(conn)
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/prompts")
    assert resp.status_code == 200
    data = resp.json()
    assert "prompts" in data
    assert len(data["prompts"]) > 0
    prompt = data["prompts"][0]
    assert "id" in prompt
    assert "name" in prompt
    assert "template" in prompt
    assert "version" in prompt


def test_get_prompt_by_name(monkeypatch, tmp_path):
    db_path = tmp_path / "prompts_get.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        seed_prompts(conn)
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/prompts/triage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "triage"
    assert "template" in data


def test_get_prompt_not_found(monkeypatch, tmp_path):
    db_path = tmp_path / "prompts_notfound.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    client = TestClient(app)
    resp = client.get("/api/prompts/nonexistent")
    assert resp.status_code == 200
    assert resp.json()["error"] == "Prompt not found"


def test_update_prompt(monkeypatch, tmp_path):
    db_path = tmp_path / "prompts_update.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        seed_prompts(conn)
        conn.commit()

    client = TestClient(app)
    resp = client.put("/api/prompts/triage", json={"template": "new template", "updated_by": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "triage"
    assert data["version"] == 2


def test_prompt_history(monkeypatch, tmp_path):
    db_path = tmp_path / "prompts_history.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        seed_prompts(conn)
        conn.commit()

    client = TestClient(app)
    # Update to create history
    client.put("/api/prompts/triage", json={"template": "v2 template"})

    resp = client.get("/api/prompts/triage/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "triage"
    assert len(data["history"]) >= 1


def test_prompt_rollback(monkeypatch, tmp_path):
    db_path = tmp_path / "prompts_rollback.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    with get_connection(db_path) as conn:
        seed_prompts(conn)
        conn.commit()

    client = TestClient(app)
    # Update then rollback
    client.put("/api/prompts/triage", json={"template": "v2 template"})
    resp = client.post("/api/prompts/triage/rollback", params={"version": 1})
    assert resp.status_code == 200
    assert "Rolled back" in resp.json()["message"]
