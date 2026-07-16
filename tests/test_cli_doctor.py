"""Doctor health-check CLI regressions."""

from click.testing import CliRunner

from twag.cli import cli


def test_doctor_quiet_is_silent_and_nonzero_for_unhealthy_scratch_runtime(monkeypatch):
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CT0", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = CliRunner().invoke(cli, ["doctor", "--quiet"])
    assert result.exit_code != 0
    assert result.output == ""
