"""Shared pytest fixtures for twag tests."""

import sys
from pathlib import Path

import pytest

# Add the package to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def isolate_twag_runtime(monkeypatch, tmp_path):
    """Keep every test away from this machine's deployed database and config."""
    monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path / "twag-data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    from twag import config

    config._config_cache = None
    yield
    config._config_cache = None
