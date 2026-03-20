"""Tests for twag.config."""

import json
from pathlib import Path

from twag.config import (
    DEFAULT_CONFIG,
    deep_merge,
    get_data_dir,
    get_xdg_config_home,
    get_xdg_data_home,
    load_config,
)


class TestDeepMerge:
    def test_simple_override(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        assert deep_merge(base, override) == {"a": 1, "b": 3}

    def test_nested_merge(self):
        base = {"outer": {"a": 1, "b": 2}}
        override = {"outer": {"b": 99}}
        result = deep_merge(base, override)
        assert result == {"outer": {"a": 1, "b": 99}}

    def test_new_key_added(self):
        base = {"a": 1}
        override = {"b": 2}
        assert deep_merge(base, override) == {"a": 1, "b": 2}

    def test_base_unmodified(self):
        base = {"a": 1}
        override = {"a": 2}
        deep_merge(base, override)
        assert base == {"a": 1}

    def test_nested_new_key(self):
        base = {"outer": {"a": 1}}
        override = {"outer": {"new_key": "val"}}
        result = deep_merge(base, override)
        assert result["outer"]["new_key"] == "val"
        assert result["outer"]["a"] == 1


class TestLoadConfig:
    def test_no_file_returns_defaults(self, monkeypatch, tmp_path):
        monkeypatch.setattr("twag.config.get_config_path", lambda: tmp_path / "missing" / "config.json")
        config = load_config()
        assert config["llm"]["triage_model"] == DEFAULT_CONFIG["llm"]["triage_model"]

    def test_file_merges_with_defaults(self, monkeypatch, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"scoring": {"min_score_for_digest": 99}}))
        monkeypatch.setattr("twag.config.get_config_path", lambda: config_path)
        config = load_config()
        assert config["scoring"]["min_score_for_digest"] == 99
        # Other defaults still present
        assert config["scoring"]["batch_size"] == DEFAULT_CONFIG["scoring"]["batch_size"]


class TestGetXdgPaths:
    def test_xdg_config_home_env(self, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/config")
        assert get_xdg_config_home() == Path("/custom/config")

    def test_xdg_config_home_default(self, monkeypatch):
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = get_xdg_config_home()
        assert result == Path.home() / ".config"

    def test_xdg_data_home_env(self, monkeypatch):
        monkeypatch.setenv("XDG_DATA_HOME", "/custom/data")
        assert get_xdg_data_home() == Path("/custom/data")

    def test_xdg_data_home_default(self, monkeypatch):
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        result = get_xdg_data_home()
        assert result == Path.home() / ".local" / "share"


class TestGetDataDir:
    def test_env_var_priority(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path / "env_data"))
        assert get_data_dir() == tmp_path / "env_data"

    def test_config_override(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TWAG_DATA_DIR", raising=False)
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"paths": {"data_dir": str(tmp_path / "cfg_data")}}))
        monkeypatch.setattr("twag.config.get_config_path", lambda: config_path)
        assert get_data_dir() == tmp_path / "cfg_data"

    def test_xdg_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TWAG_DATA_DIR", raising=False)
        monkeypatch.setattr("twag.config.get_config_path", lambda: tmp_path / "missing.json")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        assert get_data_dir() == tmp_path / "twag"
