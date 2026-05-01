"""CLI command for metrics coverage summary."""

from __future__ import annotations

from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.table import Table

from ..metrics import get_collector
from ..metrics_coverage import CoverageReport, analyze_coverage


@click.command("metrics")
@click.option(
    "--analyze",
    "analyze",
    is_flag=True,
    help="Run a static AST scan of the source tree instead of showing runtime data.",
)
def metrics(analyze: bool) -> None:
    """Show metrics instrumentation coverage summary."""
    console = Console()
    if analyze:
        _render_static_coverage(console)
        return
    _render_runtime_coverage(console)


def _render_runtime_coverage(console: Console) -> None:
    m = get_collector()
    snap = m.snapshot()
    subsystems = m.instrumented_subsystems()

    coverage = Table(title="Metrics Coverage")
    coverage.add_column("Subsystem", style="cyan")
    coverage.add_column("Instrumented", justify="center")

    all_subsystems = {
        "scorer": "LLM scoring (latency, tokens, errors, retries)",
        "pipeline": "Pipeline processing (batch timing, triage counts)",
        "fetcher": "Tweet fetching (latency, retries, errors)",
        "web": "Web layer (request count, latency)",
    }
    for name, description in all_subsystems.items():
        active = subsystems.get(name, False)
        status = "[green]yes[/green]" if active else "[dim]no data yet[/dim]"
        coverage.add_row(f"{name} — {description}", status)

    console.print(coverage)

    if snap["counters"]:
        counters = Table(title="Counters")
        counters.add_column("Name", style="cyan")
        counters.add_column("Value", justify="right")
        for name, value in sorted(snap["counters"].items()):
            counters.add_row(name, f"{value:,.0f}")
        console.print(counters)

    if snap["histograms"]:
        histograms = Table(title="Histograms")
        histograms.add_column("Name", style="cyan")
        histograms.add_column("Count", justify="right")
        histograms.add_column("Mean", justify="right")
        histograms.add_column("P50", justify="right")
        histograms.add_column("P99", justify="right")
        for name, stats in sorted(snap["histograms"].items()):
            histograms.add_row(
                name,
                f"{stats['count']:,.0f}",
                f"{stats['mean']:.3f}",
                f"{stats['p50']:.3f}",
                f"{stats['p99']:.3f}",
            )
        console.print(histograms)

    if not snap["counters"] and not snap["histograms"]:
        console.print("[dim]No metrics recorded yet. Run fetch/process/web to generate data.[/dim]")


def _render_static_coverage(console: Console) -> None:
    root = Path(__file__).resolve().parents[1]
    report: CoverageReport = analyze_coverage(root)

    summary = Table(title=f"Static Metrics Coverage — {report.coverage_pct:.0f}%")
    summary.add_column("Subsystem", style="cyan")
    summary.add_column("Modules", justify="right")
    summary.add_column("Call sites", justify="right")
    summary.add_column("Distinct metrics", justify="right")
    summary.add_column("Mismatches", justify="right")

    for name, cov in report.subsystems.items():
        total = cov.total_modules or 0
        ratio = f"{len(cov.instrumented_modules)}/{total}" if total else "—"
        mismatches = f"[red]{len(cov.prefix_mismatches)}[/red]" if cov.prefix_mismatches else "0"
        summary.add_row(
            f"{name} — {cov.description}",
            ratio,
            str(cov.call_sites),
            str(len(cov.metric_names)),
            mismatches,
        )
    console.print(summary)

    if report.uninstrumented_modules:
        gaps = Table(title="Uninstrumented modules (in tracked subsystems)")
        gaps.add_column("Module", style="yellow")
        for module in report.uninstrumented_modules:
            gaps.add_row(module)
        console.print(gaps)

    mismatches = [site for cov in report.subsystems.values() for site in cov.prefix_mismatches]
    if mismatches:
        warn = Table(title="Prefix mismatches (path subsystem != metric prefix)")
        warn.add_column("File", style="cyan")
        warn.add_column("Line", justify="right")
        warn.add_column("Metric", style="yellow")
        warn.add_column("Path subsystem")
        warn.add_column("Metric subsystem")
        for site in mismatches:
            warn.add_row(
                site.file,
                str(site.lineno),
                site.metric_name or "—",
                site.inferred_subsystem or "—",
                site.name_subsystem or "—",
            )
        console.print(warn)
