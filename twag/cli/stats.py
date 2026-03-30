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


@click.command("bus-factor")
@click.option("--path", "-p", type=click.Path(exists=True), default=".", help="Path to git repo")
@click.option("--ext", "-e", multiple=True, help="Filter by file extension (e.g. .py .js)")
@click.option("--top", "-n", type=int, default=20, help="Show top N modules")
def bus_factor(path: str, ext: tuple[str, ...], top: int):
    """Analyze code ownership concentration (bus factor)."""
    from ..bus_factor import analyze_repo

    extensions = set(ext) if ext else None
    modules, repo_bf = analyze_repo(repo_path=path, extensions=extensions)

    # Show repo-wide bus factor
    risk_style = {"HIGH": "bold red", "MEDIUM": "yellow", "LOW": "green"}
    repo_risk = "HIGH" if repo_bf <= 1 else ("MEDIUM" if repo_bf <= 2 else "LOW")
    console.print(f"\nRepo-wide bus factor: [bold]{repo_bf}[/bold]  [{risk_style[repo_risk]}]{repo_risk}[/]")
    console.print()

    # Filter to directory-level modules and sort by risk
    dir_modules = sorted(
        ((p, s) for p, s in modules.items() if p.endswith("/")),
        key=lambda x: (x[1].bus_factor, -x[1].total_lines),
    )[:top]

    table = Table(title="Module ownership concentration")
    table.add_column("Module", style="bold")
    table.add_column("Lines", justify="right")
    table.add_column("Dominant Author")
    table.add_column("Ownership %", justify="right")
    table.add_column("Bus Factor", justify="right")
    table.add_column("Risk")

    for mod_path, mod_stats in dir_modules:
        author, pct = mod_stats.dominant_author
        risk = mod_stats.risk_level
        style = risk_style.get(risk, "")
        table.add_row(
            mod_path,
            str(mod_stats.total_lines),
            author,
            f"{pct:.0f}%",
            str(mod_stats.bus_factor),
            f"[{style}]{risk}[/]",
        )

    console.print(table)
