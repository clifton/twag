"""CLI command for cost attribution estimation."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import rich_click as click
from rich.table import Table

from ..config import load_config
from ..costs import (
    Component,
    estimate_costs,
    load_pricing_overrides,
    total_usd,
)
from ..db import get_connection
from ..metrics import ensure_metrics_table, get_collector
from ._console import console


def _build_snapshot_from_db(window: timedelta) -> dict[str, Any]:
    """Reconstruct a metrics snapshot from the persisted ``metrics`` table.

    Counter rows are deltas (see ``MetricsCollector.flush_to_db``), so summing
    them across the window recovers the true total — even across multiple
    process lifetimes that flushed within the same window. Histograms use the
    latest row in the window (each flushed snapshot is itself cumulative for
    the writing process).
    """
    cutoff = datetime.now(timezone.utc) - window
    # Match the table's strftime format: %f is milliseconds in SQLite, fractional in Python.
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%S.") + f"{cutoff.microsecond // 1000:03d}Z"

    counters: dict[str, float] = defaultdict(float)
    histograms: dict[str, dict[str, float]] = {}

    with get_connection(readonly=True) as conn:
        ensure_metrics_table(conn)
        rows = conn.execute(
            "SELECT name, type, value, labels_json FROM metrics WHERE recorded_at >= ? ORDER BY recorded_at ASC",
            (cutoff_iso,),
        ).fetchall()

    for row in rows:
        name = row["name"]
        kind = row["type"]
        value = row["value"]
        if kind == "counter":
            counters[name] += value
        elif kind == "histogram" and row["labels_json"]:
            try:
                stats = json.loads(row["labels_json"])
            except json.JSONDecodeError:
                continue
            # Latest histogram row in the window wins (rows are ordered ASC).
            histograms[name] = stats

    return {"counters": dict(counters), "histograms": histograms}


def _component_to_dict(c: Component) -> dict[str, Any]:
    return {
        "name": c.name,
        "usd_estimate": c.usd_estimate,
        "breakdown": c.breakdown,
        "notes": c.notes,
    }


@click.command("costs")
@click.option(
    "--since",
    "since",
    default="24h",
    help="Time window for persisted metrics (e.g., 1h, 24h, 7d). Use 'live' for in-memory only.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit raw estimate as JSON.")
@click.option(
    "--pricing-file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Path to pricing override JSON. Defaults to ~/.config/twag/pricing.json if present.",
)
def costs(since: str, as_json: bool, pricing_file: str | None) -> None:
    """Estimate API costs by component from locally-tracked metrics."""
    if since == "live":
        snapshot = get_collector().snapshot()
    else:
        try:
            window = _parse_window(since)
        except ValueError as e:
            raise click.BadParameter(str(e), param_hint="--since") from e
        snapshot = _build_snapshot_from_db(window)

    overrides = load_pricing_overrides(pricing_file)

    cfg = load_config().get("llm", {})
    configured = {
        "triage": cfg.get("triage_model"),
        "enrichment": cfg.get("enrichment_model"),
        "vision": cfg.get("vision_model"),
    }

    components = estimate_costs(snapshot, pricing=overrides or None, configured_models=configured)

    if as_json:
        payload = {
            "window": since,
            "total_usd": total_usd(components),
            "components": [_component_to_dict(c) for c in components],
        }
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    table = Table(title=f"Estimated costs ({since})")
    table.add_column("Component", style="cyan")
    table.add_column("Calls", justify="right")
    table.add_column("Tokens (in)", justify="right")
    table.add_column("Tokens (out)", justify="right")
    table.add_column("USD", justify="right")
    table.add_column("Notes", style="dim")

    for c in components:
        b = c.breakdown
        calls = _fmt_int(b.get("calls", 0))
        in_tokens = _fmt_int(b.get("input_tokens", 0))
        out_tokens = _fmt_int(b.get("output_tokens", 0))
        usd = f"${c.usd_estimate:,.4f}" if c.usd_estimate else "$0.0000"
        table.add_row(c.name, calls, in_tokens, out_tokens, usd, c.notes or "")

    table.add_section()
    table.add_row("[bold]TOTAL[/bold]", "", "", "", f"[bold]${total_usd(components):,.4f}[/bold]", "")
    console.print(table)
    console.print(
        "[dim]Estimates are advisory and based on locally-tracked token counters. "
        "Calls without SDK-reported usage data are not priced.[/dim]",
    )


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return str(value)


def _parse_window(spec: str) -> timedelta:
    spec = spec.strip().lower()
    if not spec:
        raise ValueError("empty window")
    unit = spec[-1]
    try:
        n = int(spec[:-1])
    except ValueError as e:
        raise ValueError(f"could not parse window '{spec}'; use forms like 1h, 24h, 7d") from e
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    if unit == "m":
        return timedelta(minutes=n)
    raise ValueError(f"unsupported window unit '{unit}'; use m/h/d")
