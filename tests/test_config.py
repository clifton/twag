"""Tests for twag.config — deep_merge, path helpers, and config round-trip."""

import json

from twag.config import deep_merge, get_config_path, get_database_path, load_config, save_config


def test_deep_merge_flat():
    assert deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_deep_merge_override():
    assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}


def test_deep_merge_nested():
    base = {"x": {"a": 1, "b": 2}}
    override = {"x": {"b": 3, "c": 4}}
    result = deep_merge(base, override)
    assert result == {"x": {"a": 1, "b": 3, "c": 4}}


def test_deep_merge_empty_override():
    base = {"a": 1}
    assert deep_merge(base, {}) == {"a": 1}


def test_deep_merge_empty_base():
    assert deep_merge({}, {"a": 1}) == {"a": 1}


def test_deep_merge_override_replaces_non_dict_with_dict():
    base = {"a": 1}
    override = {"a": {"nested": True}}
    assert deep_merge(base, override) == {"a": {"nested": True}}


def test_get_database_path_uses_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))
    result = get_database_path()
    assert result == tmp_path / "twag.db"


def test_get_config_path_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = get_config_path()
    assert result == tmp_path / "twag" / "config.json"


def test_load_save_config_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config_path = tmp_path / "twag" / "config.json"
    config_path.parent.mkdir(parents=True)

    custom = {"llm": {"triage_model": "custom-model"}, "custom_key": "value"}
    config_path.write_text(json.dumps(custom))

    loaded = load_config()
    assert loaded["llm"]["triage_model"] == "custom-model"
    assert loaded["custom_key"] == "value"
    # Default keys still present
    assert "scoring" in loaded

    save_config(loaded)
    reloaded = json.loads(config_path.read_text())
    assert reloaded["llm"]["triage_model"] == "custom-model"
