"""Tests for context command API routes."""

from fastapi.testclient import TestClient

from twag.web.app import create_app


def test_list_context_commands_empty(monkeypatch, tmp_path):
    db_path = tmp_path / "context_list.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    client = TestClient(app)
    resp = client.get("/api/context-commands")
    assert resp.status_code == 200
    data = resp.json()
    assert "commands" in data
    assert data["commands"] == []


def test_create_context_command(monkeypatch, tmp_path):
    db_path = tmp_path / "context_create.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    client = TestClient(app)
    resp = client.post(
        "/api/context-commands",
        json={
            "name": "test_cmd",
            "command_template": "echo {tweet_id}",
            "description": "Test command",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "test_cmd"
    assert "id" in data


def test_get_context_command(monkeypatch, tmp_path):
    db_path = tmp_path / "context_get.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    client = TestClient(app)
    client.post(
        "/api/context-commands",
        json={"name": "my_cmd", "command_template": "echo hello"},
    )

    resp = client.get("/api/context-commands/my_cmd")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "my_cmd"
    assert data["command_template"] == "echo hello"
    assert data["enabled"] is True


def test_get_context_command_not_found(monkeypatch, tmp_path):
    db_path = tmp_path / "context_notfound.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    client = TestClient(app)
    resp = client.get("/api/context-commands/nonexistent")
    assert resp.status_code == 200
    assert resp.json()["error"] == "Context command not found"


def test_delete_context_command(monkeypatch, tmp_path):
    db_path = tmp_path / "context_delete.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    client = TestClient(app)
    client.post(
        "/api/context-commands",
        json={"name": "to_delete", "command_template": "echo bye"},
    )

    resp = client.delete("/api/context-commands/to_delete")
    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"]


def test_toggle_context_command(monkeypatch, tmp_path):
    db_path = tmp_path / "context_toggle.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    app = create_app()

    client = TestClient(app)
    client.post(
        "/api/context-commands",
        json={"name": "toggler", "command_template": "echo test"},
    )

    resp = client.post("/api/context-commands/toggler/toggle", params={"enabled": False})
    assert resp.status_code == 200
    assert "disabled" in resp.json()["message"]

    resp = client.get("/api/context-commands/toggler")
    assert resp.json()["enabled"] is False
