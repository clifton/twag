from click.testing import CliRunner

from twag.cli import cli


def test_cli_writes_command_lifecycle_log(tmp_path, monkeypatch) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("TWAG_LOG_DIR", str(log_dir))

    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    logs = list(log_dir.glob("cli-*.log"))
    assert len(logs) == 1
    content = logs[0].read_text()
    assert "command_start" in content
    assert "command_exit code=0" in content
    assert "--version" in content


def test_cli_does_not_write_default_log_under_pytest(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TWAG_LOG_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert not (tmp_path / "twag" / "logs").exists()
