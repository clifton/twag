"""Doctor health-check CLI regressions."""

import os

from click.testing import CliRunner

from twag.cli import cli


def test_doctor_quiet_is_silent_and_nonzero_for_unhealthy_scratch_runtime(monkeypatch):
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CT0", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = CliRunner().invoke(cli, ["doctor", "--quiet"])
    assert result.exit_code != 0
    assert result.output == ""


def _seed_context_candidates(monkeypatch, tmp_path):
    """Point the loader's candidate paths at tmp files: stale stopgap, fresh generated."""
    import twag.scorer.scoring as scoring

    stopgap = tmp_path / "twag-context.md"
    generated = tmp_path / "CONTEXT.md"
    stopgap.write_text("stopgap")
    generated.write_text("generated")
    os.utime(stopgap, (1, 1))
    monkeypatch.setattr(scoring, "FUND_CONTEXT_PATH", stopgap)
    monkeypatch.setattr(scoring, "GENERATED_FUND_CONTEXT_PATH", generated)
    return stopgap, generated


def test_doctor_context_fresh_when_only_generated_candidate_is_fresh(monkeypatch, tmp_path):
    """Doctor must watch the same candidate set as load_fund_context, not just the stopgap."""
    _seed_context_candidates(monkeypatch, tmp_path)
    result = CliRunner().invoke(cli, ["doctor"])
    assert "Context is fresh" in result.output
    assert "Context is stale" not in result.output


def test_doctor_context_stale_when_both_candidates_stale(monkeypatch, tmp_path):
    _, generated = _seed_context_candidates(monkeypatch, tmp_path)
    os.utime(generated, (1, 1))
    result = CliRunner().invoke(cli, ["doctor"])
    assert "Context is stale" in result.output
