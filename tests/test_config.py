"""Tests for twag.config."""

import json

from twag.config import deep_merge, get_data_dir, load_config


class TestDeepMerge:
    def test_nested_override(self):
        base = {"a": {"b": 1, "c": 2}}
        override = {"a": {"b": 99}}
        result = deep_merge(base, override)
        assert result["a"]["b"] == 99
        assert result["a"]["c"] == 2

    def test_new_keys(self):
        base = {"a": 1}
        override = {"b": 2}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 2}

    def test_non_dict_override(self):
        base = {"a": {"b": 1}}
        override = {"a": "replaced"}
        result = deep_merge(base, override)
        assert result["a"] == "replaced"

    def test_empty_override(self):
        base = {"a": 1}
        result = deep_merge(base, {})
        assert result == {"a": 1}

    def test_base_not_mutated(self):
        base = {"a": {"b": 1}}
        deep_merge(base, {"a": {"b": 2}})
        assert base["a"]["b"] == 1


class TestLoadConfig:
    def test_defaults_without_file(self, tmp_path, monkeypatch):
        # Point XDG config to a dir with no config file
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        config = load_config()
        assert "scoring" in config
        assert config["scoring"]["alert_threshold"] == 8

    def test_merge_with_user_file(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "twag"
        config_dir.mkdir()
        user_config = {"scoring": {"alert_threshold": 5}}
        (config_dir / "config.json").write_text(json.dumps(user_config))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        config = load_config()
        assert config["scoring"]["alert_threshold"] == 5
        # Other defaults preserved
        assert config["scoring"]["min_score_for_digest"] == 5


class TestGetDataDir:
    def test_env_var_priority(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path / "custom"))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no-config"))
        result = get_data_dir()
        assert result == tmp_path / "custom"

    def test_config_override(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TWAG_DATA_DIR", raising=False)
        config_dir = tmp_path / "twag"
        config_dir.mkdir()
        user_config = {"paths": {"data_dir": str(tmp_path / "from-config")}}
        (config_dir / "config.json").write_text(json.dumps(user_config))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        result = get_data_dir()
        assert result == tmp_path / "from-config"

    def test_xdg_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TWAG_DATA_DIR", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no-config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        result = get_data_dir()
        assert result == tmp_path / "data" / "twag"
