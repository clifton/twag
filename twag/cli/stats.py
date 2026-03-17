"""Stats, prune, and export commands."""

import json
from datetime import datetime

import rich_click as click
from rich.table import Table

from ..db import (
    archive_stale_narratives,
    get_connection,
    get_cost_by_component,
    get_cost_summary,
    get_processed_counts,
    get_total_cost,
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


def _format_cost(cost: float) -> str:
    """Format a USD cost value for display."""
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _format_tokens(count: int | None) -> str:
    """Format token counts with K/M suffixes."""
    if not count:
        return "0"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


@click.command()
@click.option(
    "--period",
    type=click.Choice(["today", "7d", "30d", "all"]),
    default="7d",
    help="Time period for cost breakdown",
)
@click.option("--by-model", is_flag=True, help="Show breakdown by model")
def costs(period: str, by_model: bool):
    """Show LLM cost breakdown by component and model."""
    days_map = {"today": 1, "7d": 7, "30d": 30, "all": None}
    days = days_map[period]

    with get_connection(readonly=True) as conn:
        total = get_total_cost(conn, days=days)

        if by_model:
            rows = get_cost_summary(conn, days=days)
        else:
            rows = get_cost_by_component(conn, days=days)

    if not rows:
        console.print(f"No LLM usage recorded ({period}).")
        return

    title = f"LLM costs ({period})"
    table = Table(title=title)

    if by_model:
        table.add_column("Component", style="bold")
        table.add_column("Provider")
        table.add_column("Model")
        table.add_column("Calls", justify="right")
        table.add_column("Input", justify="right")
        table.add_column("Output", justify="right")
        table.add_column("Cost", justify="right", style="green")

        for row in rows:
            table.add_row(
                row["component"],
                row["provider"],
                row["model"],
                str(row["calls"]),
                _format_tokens(row["total_input_tokens"]),
                _format_tokens(row["total_output_tokens"]),
                _format_cost(row["total_cost_usd"]),
            )
    else:
        table.add_column("Component", style="bold")
        table.add_column("Calls", justify="right")
        table.add_column("Input", justify="right")
        table.add_column("Output", justify="right")
        table.add_column("Cost", justify="right", style="green")

        for row in rows:
            table.add_row(
                row["component"],
                str(row["calls"]),
                _format_tokens(row["total_input_tokens"]),
                _format_tokens(row["total_output_tokens"]),
                _format_cost(row["total_cost_usd"]),
            )

    console.print(table)
    console.print(f"\nTotal estimated cost ({period}): [bold green]{_format_cost(total)}[/bold green]")
