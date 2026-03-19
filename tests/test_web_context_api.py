"""API contract tests for context-commands endpoints."""

from fastapi.testclient import TestClient

from twag.db import get_connection, upsert_context_command
from twag.web.app import create_app


def _setup_app(monkeypatch, tmp_path, db_name="twag_context_test.db"):
    db_path = tmp_path / db_name
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()
    return app, db_path


def test_list_context_commands_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_context_command(conn, "lookup", "echo {ticker}", "Lookup ticker", True)
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/context-commands")
    assert resp.status_code == 200
    data = resp.json()
    assert "commands" in data
    assert isinstance(data["commands"], list)
    assert len(data["commands"]) >= 1
    cmd = data["commands"][0]
    assert "id" in cmd
    assert "name" in cmd
    assert "command_template" in cmd
    assert "enabled" in cmd


def test_create_context_command_returns_expected_shape(monkeypatch, tmp_path):
    app, _ = _setup_app(monkeypatch, tmp_path)
    client = TestClient(app)
    resp = client.post(
        "/api/context-commands",
        json={
            "name": "price",
            "command_template": "echo {ticker}",
            "description": "Get price",
            "enabled": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["name"] == "price"
    assert data["message"] == "Context command created"


def test_get_context_command_by_name(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_context_command(conn, "lookup", "echo {ticker}", "Lookup", True)
        conn.commit()

    client = TestClient(app)
    resp = client.get("/api/context-commands/lookup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "lookup"
    assert "command_template" in data
    assert "enabled" in data


def test_get_context_command_not_found(monkeypatch, tmp_path):
    app, _ = _setup_app(monkeypatch, tmp_path)
    client = TestClient(app)
    resp = client.get("/api/context-commands/nonexistent")
    assert resp.status_code == 200
    assert "error" in resp.json()


def test_update_context_command_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_context_command(conn, "lookup", "echo {ticker}", "Lookup", True)
        conn.commit()

    client = TestClient(app)
    resp = client.put(
        "/api/context-commands/lookup",
        json={
            "name": "lookup",
            "command_template": "curl {ticker}",
            "description": "Updated lookup",
            "enabled": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "lookup"
    assert data["message"] == "Context command updated"


def test_delete_context_command_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_context_command(conn, "lookup", "echo {ticker}", "Lookup", True)
        conn.commit()

    client = TestClient(app)
    resp = client.delete("/api/context-commands/lookup")
    assert resp.status_code == 200
    assert "message" in resp.json()

    # Deleting again should return error
    resp2 = client.delete("/api/context-commands/lookup")
    assert resp2.status_code == 200
    assert "error" in resp2.json()


def test_toggle_context_command_returns_expected_shape(monkeypatch, tmp_path):
    app, db_path = _setup_app(monkeypatch, tmp_path)
    with get_connection(db_path) as conn:
        upsert_context_command(conn, "lookup", "echo {ticker}", "Lookup", True)
        conn.commit()

    client = TestClient(app)
    resp = client.post("/api/context-commands/lookup/toggle", params={"enabled": False})
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert "disabled" in data["message"]


def test_toggle_context_command_not_found(monkeypatch, tmp_path):
    app, _ = _setup_app(monkeypatch, tmp_path)
    client = TestClient(app)
    resp = client.post("/api/context-commands/nonexistent/toggle", params={"enabled": True})
    assert resp.status_code == 200
    assert "error" in resp.json()
