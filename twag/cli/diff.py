"""CLI command for semantic diff explanation."""

import subprocess

import rich_click as click

from ..config import load_config
from ..scorer.diff_prompt import DIFF_EXPLAIN_PROMPT
from ..scorer.llm_client import _call_llm


@click.command()
@click.argument("ref_range", default="HEAD~1..HEAD")
def diff(ref_range: str) -> None:
    """Explain what a set of code changes do semantically.

    REF_RANGE is a git revision range (default: HEAD~1..HEAD).
    """
    try:
        result = subprocess.run(
            ["git", "diff", ref_range],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(f"git diff failed: {exc.stderr.strip()}") from exc

    diff_text = result.stdout
    if not diff_text.strip():
        click.echo("No diff output for the given range.")
        return

    config = load_config()
    provider = config["llm"].get("triage_provider", "gemini")
    model = config["llm"]["triage_model"]

    prompt = DIFF_EXPLAIN_PROMPT.format(diff=diff_text)
    explanation = _call_llm(provider, model, prompt, max_tokens=4096)
    click.echo(explanation)
