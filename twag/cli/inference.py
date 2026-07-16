"""Inference usage and cost analysis commands."""

import rich_click as click
from rich.console import Console
from rich.table import Table

from ..db import init_db, summarize_llm_usage


def _fmt_int(value) -> str:
    return f"{int(value or 0):,}"


def _fmt_float(value, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.{digits}f}"


def _fmt_cost(value) -> str:
    return f"${float(value or 0):,.4f}"


@click.group("inference")
def inference() -> None:
    """Analyze persistent LLM inference usage."""


@inference.command("usage")
@click.option("--days", type=int, default=30, show_default=True, help="Days of usage to include.")
@click.option("--all-time", is_flag=True, help="Ignore --days and include all logged usage.")
@click.option("--provider", help="Filter by provider.")
@click.option("--model", help="Filter by model.")
@click.option("--component", help="Filter by component, e.g. triage, enrichment, vision.")
def usage(days: int, all_time: bool, provider: str | None, model: str | None, component: str | None) -> None:
    """Show token usage and estimated cost by provider/model/component."""
    output = Console(width=160)
    init_db()
    rows = summarize_llm_usage(
        days=None if all_time else days,
        provider=provider,
        model=model,
        component=component,
    )

    title = "LLM Inference Usage"
    if not all_time:
        title += f" - last {days}d"

    if not rows:
        output.print(f"[dim]No LLM usage rows found for {title.lower()}.[/dim]")
        return

    table = Table(title=title)
    table.add_column("Component", style="cyan", overflow="fold")
    table.add_column("Provider", overflow="fold")
    table.add_column("Model", overflow="fold")
    table.add_column("Calls", justify="right")
    table.add_column("Fail", justify="right")
    table.add_column("Input", justify="right")
    table.add_column("Cached", justify="right")
    table.add_column("Output", justify="right")
    table.add_column("Think", justify="right")
    table.add_column("Est. Cost", justify="right")
    table.add_column("Avg s", justify="right")

    totals = {
        "calls": 0,
        "failures": 0,
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "reestimated_cost_usd": 0.0,
    }

    for row in rows:
        for key in totals:
            totals[key] += row.get(key) or 0

        table.add_row(
            str(row["component"]),
            str(row["provider"]),
            str(row["model"]),
            _fmt_int(row["calls"]),
            _fmt_int(row["failures"]),
            _fmt_int(row["input_tokens"]),
            _fmt_int(row["cached_input_tokens"]),
            _fmt_int(row["output_tokens"]),
            _fmt_int(row["reasoning_tokens"]),
            _fmt_cost(row["reestimated_cost_usd"]),
            _fmt_float(row["avg_latency_seconds"]),
        )

    table.add_section()
    table.add_row(
        "TOTAL",
        "",
        "",
        _fmt_int(totals["calls"]),
        _fmt_int(totals["failures"]),
        _fmt_int(totals["input_tokens"]),
        _fmt_int(totals["cached_input_tokens"]),
        _fmt_int(totals["output_tokens"]),
        _fmt_int(totals["reasoning_tokens"]),
        _fmt_cost(totals["reestimated_cost_usd"]),
        "",
    )
    output.print(table)
    output.print(
        "[dim]Cost is estimated from the local price table and excludes grounding/search and billing credits.[/dim]",
    )
