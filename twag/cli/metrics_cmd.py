"""CLI command for metrics coverage summary."""

from __future__ import annotations

import rich_click as click
from rich.console import Console
from rich.table import Table

from ..metrics import get_collector


@click.command("metrics")
def metrics() -> None:
    """Show metrics instrumentation coverage summary."""
    console = Console()
    m = get_collector()
    snap = m.snapshot()
    subsystems = m.instrumented_subsystems()

    # Coverage table
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

    # Current counters
    if snap["counters"]:
        counters = Table(title="Counters")
        counters.add_column("Name", style="cyan")
        counters.add_column("Value", justify="right")
        for name, value in sorted(snap["counters"].items()):
            counters.add_row(name, f"{value:,.0f}")
        console.print(counters)

    # Current histograms
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
