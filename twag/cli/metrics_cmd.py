"""CLI command for metrics coverage summary."""

import rich_click as click
from rich.table import Table

from ..metrics import get_collector
from ._console import console


@click.command("metrics")
def metrics():
    """Show metrics instrumentation coverage summary."""
    collector = get_collector()
    coverage = collector.subsystem_coverage()
    snapshot = collector.snapshot()

    table = Table(title="Metrics Coverage")
    table.add_column("Subsystem", style="bold")
    table.add_column("Instrumented", justify="center")
    table.add_column("Metrics")

    subsystem_prefixes = {
        "scorer": "llm_",
        "pipeline": "pipeline_",
        "fetcher": "fetch_",
        "web": "http_",
        "triage": "triage_",
    }

    all_keys = set(snapshot["counters"].keys()) | set(snapshot["gauges"].keys()) | set(snapshot["histograms"].keys())

    for name, prefix in subsystem_prefixes.items():
        active = coverage.get(name, False)
        matching = sorted(k for k in all_keys if k.startswith(prefix))
        icon = "[green]yes[/green]" if active else "[dim]no[/dim]"
        metric_names = ", ".join(matching) if matching else "-"
        table.add_row(name, icon, metric_names)

    console.print(table)

    total = len(snapshot["counters"]) + len(snapshot["gauges"]) + len(snapshot["histograms"])
    console.print(f"\nTotal metrics registered: {total}")
    console.print(f"Uptime: {snapshot['uptime_seconds']}s")
