"""Tests for twag.config — deep_merge, load/save, path helpers."""

import json

from twag.config import (
    deep_merge,
    get_data_dir,
    get_database_path,
    get_digests_dir,
    get_following_path,
    load_config,
    save_config,
)


class TestDeepMerge:
    def test_flat_override(self):
        assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_adds_new_keys(self):
        assert deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_nested_merge(self):
        base = {"x": {"a": 1, "b": 2}}
        override = {"x": {"b": 3, "c": 4}}
        assert deep_merge(base, override) == {"x": {"a": 1, "b": 3, "c": 4}}

    def test_override_replaces_non_dict_with_dict(self):
        assert deep_merge({"a": 1}, {"a": {"nested": True}}) == {"a": {"nested": True}}

    def test_override_replaces_dict_with_non_dict(self):
        assert deep_merge({"a": {"nested": True}}, {"a": 42}) == {"a": 42}

    def test_empty_override(self):
        base = {"a": 1}
        assert deep_merge(base, {}) == {"a": 1}

    def test_empty_base(self):
        assert deep_merge({}, {"a": 1}) == {"a": 1}

    def test_both_empty(self):
        assert deep_merge({}, {}) == {}

    def test_deeply_nested(self):
        base = {"l1": {"l2": {"l3": {"val": "old"}}}}
        override = {"l1": {"l2": {"l3": {"val": "new", "extra": True}}}}
        result = deep_merge(base, override)
        assert result["l1"]["l2"]["l3"] == {"val": "new", "extra": True}

    def test_does_not_mutate_base(self):
        base = {"a": {"b": 1}}
        deep_merge(base, {"a": {"b": 2}})
        assert base["a"]["b"] == 1


class TestLoadSaveConfig:
    def test_load_returns_defaults_when_no_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        config = load_config()
        assert "llm" in config
        assert config["scoring"]["min_score_for_digest"] == 5

    def test_save_and_load_roundtrip(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        custom = {"scoring": {"min_score_for_digest": 3}}
        save_config(custom)
        # Verify the file was written
        config_file = tmp_path / "twag" / "config.json"
        assert config_file.exists()
        assert json.loads(config_file.read_text()) == custom

    def test_load_merges_user_over_defaults(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        config_dir = tmp_path / "twag"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({"scoring": {"min_score_for_digest": 3}}))
        config = load_config()
        assert config["scoring"]["min_score_for_digest"] == 3
        # Other defaults still present
        assert config["scoring"]["high_signal_threshold"] == 7


class TestPathHelpers:
    def test_get_data_dir_from_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path / "custom"))
        assert get_data_dir() == tmp_path / "custom"

    def test_get_data_dir_xdg_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TWAG_DATA_DIR", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        assert get_data_dir() == tmp_path / "data" / "twag"

    def test_get_database_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))
        assert get_database_path() == tmp_path / "twag.db"

    def test_get_digests_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))
        assert get_digests_dir() == tmp_path / "digests"

    def test_get_following_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))
        assert get_following_path() == tmp_path / "following.txt"
