"""Tests for twag.auth — env-file parsing and API key resolution."""

from pathlib import Path

import pytest

from twag import auth


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Make `Path.home()` resolve to a tmp dir so ~/.env is sandboxed."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


class TestLoadEnvFile:
    def test_missing_file_returns_empty_dict(self, fake_home: Path) -> None:
        # Default ~/.env path doesn't exist in the sandbox.
        assert auth.load_env_file() == {}

    def test_explicit_missing_path(self, tmp_path: Path) -> None:
        assert auth.load_env_file(tmp_path / "nope.env") == {}

    def test_parses_simple_pairs(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\nBAZ=qux\n")
        assert auth.load_env_file(env_file) == {"FOO": "bar", "BAZ": "qux"}

    def test_skips_comments_and_blank_lines(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# a comment\n\nFOO=bar\n# trailing\n")
        assert auth.load_env_file(env_file) == {"FOO": "bar"}

    def test_strips_export_prefix_and_quotes(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("export TOKEN=\"abc123\"\nexport CT0='cookie'\n")
        result = auth.load_env_file(env_file)
        assert result == {"TOKEN": "abc123", "CT0": "cookie"}

    def test_lines_without_equals_are_skipped(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("not_an_assignment\nFOO=bar\n")
        assert auth.load_env_file(env_file) == {"FOO": "bar"}

    def test_value_containing_equals_is_preserved(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=foo=bar=baz\n")
        assert auth.load_env_file(env_file) == {"KEY": "foo=bar=baz"}


class TestGetApiKey:
    def test_environment_takes_precedence(
        self,
        tmp_path: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env_file = fake_home / ".env"
        env_file.write_text("MY_KEY=from-file\n")
        monkeypatch.setenv("MY_KEY", "from-env")
        assert auth.get_api_key("MY_KEY") == "from-env"

    def test_falls_back_to_env_file(
        self,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env_file = fake_home / ".env"
        env_file.write_text("MY_KEY=from-file\n")
        monkeypatch.delenv("MY_KEY", raising=False)
        assert auth.get_api_key("MY_KEY") == "from-file"

    def test_missing_raises_value_error(
        self,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("MY_KEY", raising=False)
        with pytest.raises(ValueError, match="MY_KEY not set"):
            auth.get_api_key("MY_KEY")


class TestGetAuthEnv:
    def test_merges_env_file_into_environ(
        self,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env_file = fake_home / ".env"
        env_file.write_text("AUTH_TOKEN=tok\nCT0=cookie\n")
        monkeypatch.setenv("PATH_MARKER", "preserved")
        result = auth.get_auth_env()
        assert result["AUTH_TOKEN"] == "tok"
        assert result["CT0"] == "cookie"
        assert result["PATH_MARKER"] == "preserved"

    def test_env_file_overrides_existing_variables(
        self,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env_file = fake_home / ".env"
        env_file.write_text("AUTH_TOKEN=from-file\n")
        monkeypatch.setenv("AUTH_TOKEN", "from-env")
        # load_env_file overrides since env.update(load_env_file()) runs second.
        assert auth.get_auth_env()["AUTH_TOKEN"] == "from-file"
