"""CLI command for semantic diff explanation."""

import subprocess

import rich_click as click
from rich.console import Console
from rich.markdown import Markdown


@click.command("diff")
@click.argument("ref_range", default="HEAD~1..HEAD")
@click.option("-m", "--model", default=None, help="Override LLM model.")
@click.option("-p", "--provider", default=None, help="Override LLM provider.")
def diff(ref_range: str, model: str | None, provider: str | None):
    """Explain the semantic meaning of code changes.

    REF_RANGE is a git ref range (default: HEAD~1..HEAD).
    Examples: HEAD~3..HEAD, main..feature-branch, abc123..def456
    """
    console = Console()

    result = subprocess.run(
        ["git", "diff", ref_range],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        console.print(f"[red]git diff failed:[/red] {result.stderr.strip()}")
        raise SystemExit(1)

    diff_text = result.stdout.strip()
    if not diff_text:
        console.print("[yellow]No changes found in the given range.[/yellow]")
        return

    from twag.scorer.scoring import explain_diff

    with console.status("Analyzing diff..."):
        explanation = explain_diff(diff_text, model=model, provider=provider)

    console.print(Markdown(explanation))
