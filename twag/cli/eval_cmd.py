"""Golden prompt evaluation command."""

from pathlib import Path

import rich_click as click

from ..evaluation import DEFAULT_GOLDEN_PATH, run_golden_eval


@click.group("eval")
def eval_group():
    """Evaluate scorer prompts against versioned fixtures."""


@eval_group.command("run")
@click.option("--model", help="Override the configured triage model")
@click.option("--provider", type=click.Choice(["gemini", "deepseek", "anthropic"]))
@click.option(
    "--fixture",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=DEFAULT_GOLDEN_PATH,
    show_default=True,
)
def run(model: str | None, provider: str | None, fixture: Path):
    """Run the v0 golden set; exits nonzero when calibration gates fail."""
    try:
        report = run_golden_eval(path=fixture, model=model, provider=provider)
    except Exception as exc:
        detail = str(exc).splitlines()[0][:240]
        raise click.ClickException(f"golden evaluation could not run: {type(exc).__name__}: {detail}") from exc
    click.echo(f"items: {report.total}")
    click.echo(f"score-band accuracy: {report.band_accuracy:.1%}")
    click.echo(f"surprise accuracy: {report.surprise_accuracy:.1%}")
    click.echo(f"stale-repeat accuracy: {report.stale_accuracy:.1%}")
    click.echo(f"trigger precision/recall: {report.trigger_precision:.1%}/{report.trigger_recall:.1%}")
    click.echo(f"catalyst accuracy: {report.catalyst_accuracy:.1%}")
    click.echo(f"direction accuracy: {report.direction_accuracy:.1%}")
    if not report.passed:
        raise click.ClickException("golden evaluation failed")
    click.echo("PASS")
