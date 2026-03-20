"""API contract tests for prompts endpoints."""

from fastapi.testclient import TestClient

from twag.db import get_connection, upsert_prompt
from twag.web.app import create_app


def _setup_app(monkeypatch, tmp_path, db_name="twag_prompts_test.db"):
    db_path = tmp_path / db_name
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()
    return app, db_path


def test_list_prompts_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_prompt(conn, "scoring", "Score this tweet: {content}", "system")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/prompts")
    assert resp.status_code == 200
    data = resp.json()
    assert "prompts" in data
    assert isinstance(data["prompts"], list)
    assert len(data["prompts"]) >= 1
    p = data["prompts"][0]
    assert "id" in p
    assert "name" in p
    assert "template" in p
    assert "version" in p


def test_get_prompt_by_name_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_prompt(conn, "scoring", "Score: {content}", "system")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/prompts/scoring")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "scoring"
    assert "template" in data
    assert "version" in data


def test_get_prompt_not_found(monkeypatch, tmp_path):
    app, _ = _setup_app(monkeypatch, tmp_path)
    client = TestClient(app)
    resp = client.get("/api/prompts/nonexistent")
    assert resp.status_code == 200
    assert "error" in resp.json()


def test_update_prompt_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_prompt(conn, "scoring", "v1 template", "system")
        conn.commit()

    client = TestClient(app)
    resp = client.put("/api/prompts/scoring", json={"template": "v2 template", "updated_by": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "scoring"
    assert data["version"] == 2
    assert data["message"] == "Prompt updated"


def test_prompt_history_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_prompt(conn, "scoring", "v1", "system")
        upsert_prompt(conn, "scoring", "v2", "user")
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/prompts/scoring/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "scoring"
    assert "history" in data
    assert isinstance(data["history"], list)


def test_prompt_rollback_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_prompt(conn, "scoring", "v1", "system")
        upsert_prompt(conn, "scoring", "v2", "user")
        conn.commit()

    client = TestClient(app)
    resp = client.post("/api/prompts/scoring/rollback", params={"version": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data


def test_prompt_rollback_invalid_version(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_prompt(conn, "scoring", "v1", "system")
        conn.commit()

    client = TestClient(app)
    resp = client.post("/api/prompts/scoring/rollback", params={"version": 999})
    assert resp.status_code == 200
    assert "error" in resp.json()
