"""Tests for the semantic diff CLI command."""

from unittest.mock import patch

from click.testing import CliRunner

from twag.cli import cli


def test_diff_calls_llm_with_diff_output():
    """Verify the diff command runs git diff, sends prompt to LLM, and prints result."""
    fake_diff = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new\n"
    fake_explanation = "Refactored foo.py to use new implementation."

    with (
        patch("twag.cli.diff.subprocess.run") as mock_run,
        patch("twag.cli.diff.load_config") as mock_config,
        patch("twag.cli.diff._call_llm", return_value=fake_explanation) as mock_llm,
    ):
        mock_run.return_value.stdout = fake_diff
        mock_config.return_value = {
            "llm": {"triage_provider": "gemini", "triage_model": "gemini-test"},
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["diff"])

        assert result.exit_code == 0
        assert fake_explanation in result.output

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "git" in call_args[0][0]
        assert "diff" in call_args[0][0]
        assert "HEAD~1..HEAD" in call_args[0][0]

        mock_llm.assert_called_once()
        prompt_arg = mock_llm.call_args[0][2]
        assert fake_diff in prompt_arg


def test_diff_custom_range():
    """Verify a custom ref range is forwarded to git diff."""
    fake_diff = "some diff content\n"

    with (
        patch("twag.cli.diff.subprocess.run") as mock_run,
        patch("twag.cli.diff.load_config") as mock_config,
        patch("twag.cli.diff._call_llm", return_value="explanation"),
    ):
        mock_run.return_value.stdout = fake_diff
        mock_config.return_value = {
            "llm": {"triage_provider": "gemini", "triage_model": "gemini-test"},
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["diff", "abc123..def456"])

        assert result.exit_code == 0
        call_args = mock_run.call_args
        assert "abc123..def456" in call_args[0][0]


def test_diff_empty_output():
    """When git diff returns nothing, print a message and skip the LLM call."""
    with (
        patch("twag.cli.diff.subprocess.run") as mock_run,
        patch("twag.cli.diff._call_llm") as mock_llm,
    ):
        mock_run.return_value.stdout = ""

        runner = CliRunner()
        result = runner.invoke(cli, ["diff"])

        assert result.exit_code == 0
        assert "No diff" in result.output
        mock_llm.assert_not_called()
