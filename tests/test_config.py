"""Tests for twag.config — XDG paths, config merge, and mtime cache."""

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from twag import config


@pytest.fixture(autouse=True)
def reset_config_cache() -> Iterator[None]:
    """Each test starts with a clean cache to avoid cross-test leakage."""
    config._config_cache = None
    yield
    config._config_cache = None


@pytest.fixture
def xdg_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Sandbox both XDG dirs and clear TWAG_DATA_DIR."""
    config_home = tmp_path / "config"
    data_home = tmp_path / "data"
    config_home.mkdir()
    data_home.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.delenv("TWAG_DATA_DIR", raising=False)
    return {"config": config_home, "data": data_home}


class TestXdgPaths:
    def test_xdg_config_home_uses_env(self, xdg_dirs: dict[str, Path]) -> None:
        assert config.get_xdg_config_home() == xdg_dirs["config"]

    def test_xdg_config_home_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        assert config.get_xdg_config_home() == Path.home() / ".config"

    def test_get_config_path(self, xdg_dirs: dict[str, Path]) -> None:
        assert config.get_config_path() == xdg_dirs["config"] / "twag" / "config.json"


class TestLoadConfig:
    def test_returns_defaults_when_file_missing(self, xdg_dirs: dict[str, Path]) -> None:
        loaded = config.load_config()
        assert loaded["scoring"]["alert_threshold"] == 8
        assert loaded["llm"]["max_concurrency_triage"] == 6

    def test_user_overrides_merge_with_defaults(self, xdg_dirs: dict[str, Path]) -> None:
        cfg_path = xdg_dirs["config"] / "twag" / "config.json"
        cfg_path.parent.mkdir(parents=True)
        cfg_path.write_text(json.dumps({"scoring": {"alert_threshold": 9}}))

        loaded = config.load_config()
        # Override applied:
        assert loaded["scoring"]["alert_threshold"] == 9
        # Untouched default keys still present:
        assert loaded["scoring"]["batch_size"] == 15
        # Untouched top-level sections still present:
        assert loaded["llm"]["max_concurrency_triage"] == 6

    def test_returns_deep_copy_so_callers_cannot_mutate_cache(
        self,
        xdg_dirs: dict[str, Path],
    ) -> None:
        first = config.load_config()
        first["scoring"]["alert_threshold"] = 999
        second = config.load_config()
        assert second["scoring"]["alert_threshold"] == 8

    def test_cache_invalidates_on_mtime_change(self, xdg_dirs: dict[str, Path]) -> None:
        cfg_path = xdg_dirs["config"] / "twag" / "config.json"
        cfg_path.parent.mkdir(parents=True)
        cfg_path.write_text(json.dumps({"scoring": {"alert_threshold": 1}}))

        first = config.load_config()
        assert first["scoring"]["alert_threshold"] == 1

        # Force a different mtime so the cache invalidates deterministically.
        time.sleep(0.01)
        cfg_path.write_text(json.dumps({"scoring": {"alert_threshold": 2}}))
        future = time.time() + 5
        import os

        os.utime(cfg_path, (future, future))

        second = config.load_config()
        assert second["scoring"]["alert_threshold"] == 2


class TestDeepMerge:
    def test_overrides_scalars(self) -> None:
        result = config.deep_merge({"a": 1, "b": 2}, {"b": 99})
        assert result == {"a": 1, "b": 99}

    def test_merges_nested_dicts(self) -> None:
        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 20, "z": 30}}
        assert config.deep_merge(base, override) == {"a": {"x": 1, "y": 20, "z": 30}}

    def test_override_replaces_when_types_differ(self) -> None:
        # Non-dict override on a dict key replaces rather than merges.
        result = config.deep_merge({"a": {"x": 1}}, {"a": "scalar"})
        assert result == {"a": "scalar"}


class TestDataDir:
    def test_env_var_wins(
        self,
        xdg_dirs: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path / "explicit"))
        assert config.get_data_dir() == tmp_path / "explicit"

    def test_config_file_override_used_when_env_missing(
        self,
        xdg_dirs: dict[str, Path],
        tmp_path: Path,
    ) -> None:
        cfg_path = xdg_dirs["config"] / "twag" / "config.json"
        cfg_path.parent.mkdir(parents=True)
        custom = tmp_path / "from-config"
        cfg_path.write_text(json.dumps({"paths": {"data_dir": str(custom)}}))

        assert config.get_data_dir() == custom

    def test_falls_back_to_xdg_default(self, xdg_dirs: dict[str, Path]) -> None:
        assert config.get_data_dir() == xdg_dirs["data"] / "twag"


class TestDerivedPaths:
    def test_database_path(self, xdg_dirs: dict[str, Path]) -> None:
        assert config.get_database_path() == xdg_dirs["data"] / "twag" / "twag.db"

    def test_digests_dir(self, xdg_dirs: dict[str, Path]) -> None:
        assert config.get_digests_dir() == xdg_dirs["data"] / "twag" / "digests"

    def test_following_path(self, xdg_dirs: dict[str, Path]) -> None:
        assert config.get_following_path() == xdg_dirs["data"] / "twag" / "following.txt"


class TestSaveConfig:
    def test_writes_and_creates_parent(self, xdg_dirs: dict[str, Path]) -> None:
        config.save_config({"scoring": {"alert_threshold": 7}})
        cfg_path = xdg_dirs["config"] / "twag" / "config.json"
        assert json.loads(cfg_path.read_text())["scoring"]["alert_threshold"] == 7
