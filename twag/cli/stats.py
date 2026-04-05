"""Stats, prune, and export commands."""

import json
from datetime import datetime

import rich_click as click
from rich.table import Table

from ..costs import estimate_costs, total_cost
from ..db import (
    archive_stale_narratives,
    get_connection,
    get_cost_attribution_counts,
    get_processed_counts,
    get_tweet_stats,
    prune_old_tweets,
)
from ._console import console


@click.command()
@click.option("--date", "-d", help="Date to show stats for (YYYY-MM-DD)")
@click.option("--today", is_flag=True, help="Show today's stats")
def stats(date: str | None, today: bool):
    """Show processing statistics."""
    if today:
        date = datetime.now().strftime("%Y-%m-%d")

    with get_connection(readonly=True) as conn:
        s = get_tweet_stats(conn, date=date)
        recent = get_processed_counts(conn)

    if not s or s.get("total", 0) == 0:
        console.print("No tweets found.")
        return

    period = f"for {date}" if date else "all time"

    table = Table(title=f"Tweet statistics ({period})", show_header=False)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total", str(s["total"]))
    table.add_row("Processed", str(s["processed"]))
    table.add_row("Pending", str(s["pending"]))
    table.add_row("Avg score", f"{s['avg_score']:.1f}" if s["avg_score"] else "-")
    table.add_row("High signal (\u22657)", str(s["high_signal"]))
    table.add_row("Digest worthy (\u22655)", str(s["digest_worthy"]))

    console.print(table)

    # Show recent processing activity (only for all-time stats)
    if not date:
        console.print("")
        recent_table = Table(title="Recent processing", show_header=False)
        recent_table.add_column("Period", style="bold")
        recent_table.add_column("Tweets", justify="right")

        recent_table.add_row("Last 1h", str(recent["1h"]))
        recent_table.add_row("Last 24h", str(recent["24h"]))
        recent_table.add_row("Last 7d", str(recent["7d"]))

        console.print(recent_table)


@click.command()
@click.option("--days", type=int, default=14, help="Delete tweets older than N days")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
def prune(days: int, dry_run: bool):
    """Remove old tweets from database."""
    with get_connection() as conn:
        if dry_run:
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM tweets
                WHERE created_at < datetime('now', ?)
                AND included_in_digest IS NOT NULL
                """,
                (f"-{days} days",),
            )
            count = cursor.fetchone()[0]
            console.print(f"Would delete {count} tweets older than {days} days")
        else:
            deleted = prune_old_tweets(conn, days=days)
            stale = archive_stale_narratives(conn, days=7)
            conn.commit()
            console.print(f"Deleted {deleted} old tweets, archived {stale} stale narratives")


@click.command()
@click.option("--format", "fmt", type=click.Choice(["json"]), default="json")
@click.option("--days", type=int, default=7, help="Export tweets from last N days")
def export(fmt: str, days: int):
    """Export recent data."""
    with get_connection(readonly=True) as conn:
        cursor = conn.execute(
            """
            SELECT * FROM tweets
            WHERE created_at >= datetime('now', ?)
            ORDER BY created_at DESC
            """,
            (f"-{days} days",),
        )
        tweets = [dict(row) for row in cursor.fetchall()]

    click.echo(json.dumps(tweets, indent=2, default=str))


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


@click.command()
@click.option("--date", "-d", help="Date to estimate costs for (YYYY-MM-DD)")
@click.option("--today", is_flag=True, help="Estimate today's costs")
@click.option("--model-prices", type=str, default=None, help="JSON override for model pricing")
def costs(date: str | None, today: bool, model_prices: str | None):
    """Estimate LLM API costs by pipeline component."""
    if today:
        date = datetime.now().strftime("%Y-%m-%d")

    price_overrides = None
    if model_prices:
        price_overrides = json.loads(model_prices)

    with get_connection(readonly=True) as conn:
        counts = get_cost_attribution_counts(conn, date=date)

    components = estimate_costs(counts, model_prices=price_overrides)
    total = total_cost(components)

    period = f"for {date}" if date else "all time"
    table = Table(title=f"Estimated LLM costs ({period})")
    table.add_column("Component", style="bold")
    table.add_column("Calls", justify="right")
    table.add_column("Input tokens", justify="right")
    table.add_column("Output tokens", justify="right")
    table.add_column("Est. cost", justify="right", style="green")

    for c in components:
        table.add_row(
            c.component,
            str(c.call_count),
            _fmt_tokens(c.input_tokens),
            _fmt_tokens(c.output_tokens),
            f"${c.cost_usd:.4f}",
        )

    table.add_section()
    total_in = sum(c.input_tokens for c in components)
    total_out = sum(c.output_tokens for c in components)
    total_calls = sum(c.call_count for c in components)
    table.add_row(
        "TOTAL",
        str(total_calls),
        _fmt_tokens(total_in),
        _fmt_tokens(total_out),
        f"${total:.4f}",
        style="bold",
    )

    console.print(table)
