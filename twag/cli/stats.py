"""Stats, prune, and export commands."""

import json
from datetime import datetime

import rich_click as click
from rich.table import Table

from ..db import (
    archive_stale_narratives,
    get_connection,
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
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
@click.option("--file", "dump_path", type=click.Path(), help="Write JSON to file")
def metrics(as_json: bool, dump_path: str | None):
    """Show in-memory pipeline metrics."""
    from .. import metrics as _metrics

    data = _metrics.get_all_metrics()
    counters = data.get("counters", {})
    histograms = data.get("histograms", {})

    if as_json or dump_path:
        text = _metrics.dump_json(dump_path)
        if as_json:
            click.echo(text)
        if dump_path:
            console.print(f"Metrics written to {dump_path}")
        return

    if not counters and not histograms:
        console.print("No metrics collected yet.")
        return

    if counters:
        table = Table(title="Counters", show_header=True)
        table.add_column("Name", style="bold")
        table.add_column("Value", justify="right")
        for name, value in counters.items():
            table.add_row(name, f"{value:g}")
        console.print(table)

    if histograms:
        table = Table(title="Histograms", show_header=True)
        table.add_column("Name", style="bold")
        table.add_column("Count", justify="right")
        table.add_column("Avg", justify="right")
        table.add_column("Min", justify="right")
        table.add_column("Max", justify="right")
        for name, snap in histograms.items():
            table.add_row(
                name,
                str(snap["count"]),
                f"{snap['avg']:.4f}" if snap["avg"] is not None else "-",
                f"{snap['min']:.4f}" if snap["min"] is not None else "-",
                f"{snap['max']:.4f}" if snap["max"] is not None else "-",
            )
        console.print(table)


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
