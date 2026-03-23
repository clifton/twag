"""CLI command for roadmap entropy analysis."""

from __future__ import annotations

import rich_click as click
from rich.table import Table

from ..entropy import analyze_entropy
from ._console import console

_SEVERITY_COLORS = {"low": "green", "medium": "yellow", "high": "red"}


@click.command()
@click.option("--days", default=90, show_default=True, help="Number of days of history to analyze.")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON instead of formatted report.")
def entropy(days: int, as_json: bool) -> None:
    """Analyze git history for roadmap scope creep and drift signals."""
    report = analyze_entropy(days=days)

    if as_json:
        import json

        data = {
            "overall_score": round(report.overall_score, 1),
            "commit_topic_entropy": round(report.commit_topic_entropy, 3),
            "file_churn_dispersion": round(report.file_churn_dispersion, 3),
            "surface_area_delta": report.surface_area_delta,
            "todo_accumulation": report.todo_accumulation,
            "doc_staleness_ratio": round(report.doc_staleness_ratio, 3),
            "topic_counts": report.topic_counts,
            "churn_hotspots": [{"file": f, "changes": c} for f, c in report.churn_hotspots],
            "drift_indicators": [
                {"category": d.category, "description": d.description, "severity": d.severity}
                for d in report.drift_indicators
            ],
            "recommendations": report.recommendations,
        }
        click.echo(json.dumps(data, indent=2))
        return

    # Header
    score = report.overall_score
    if score < 30:
        score_color = "green"
        score_label = "Low"
    elif score < 60:
        score_color = "yellow"
        score_label = "Moderate"
    else:
        score_color = "red"
        score_label = "High"

    console.print()
    console.print(f"[bold]Roadmap Entropy Report[/bold] (last {days} days)")
    console.print(f"Overall Score: [{score_color} bold]{score:.0f}/100[/{score_color} bold] ({score_label} entropy)")
    console.print()

    # Metrics table
    metrics = Table(title="Metrics", show_header=True)
    metrics.add_column("Metric", style="bold")
    metrics.add_column("Value", justify="right")
    metrics.add_row("Commit topic entropy", f"{report.commit_topic_entropy:.3f}")
    metrics.add_row("File churn dispersion", f"{report.file_churn_dispersion:.3f}")
    metrics.add_row("Surface area delta", f"{report.surface_area_delta:+d} files")
    metrics.add_row("TODO/FIXME count", str(report.todo_accumulation))
    metrics.add_row("Doc staleness", f"{report.doc_staleness_ratio:.0%}")
    console.print(metrics)
    console.print()

    # Topic breakdown
    if report.topic_counts:
        topics = Table(title="Commit Topics", show_header=True)
        topics.add_column("Topic", style="bold")
        topics.add_column("Count", justify="right")
        for topic, count in sorted(report.topic_counts.items(), key=lambda x: -x[1]):
            topics.add_row(topic, str(count))
        console.print(topics)
        console.print()

    # Churn hotspots
    if report.churn_hotspots:
        churn = Table(title="Churn Hotspots (top 10)", show_header=True)
        churn.add_column("File", style="bold")
        churn.add_column("Changes", justify="right")
        for filepath, count in report.churn_hotspots:
            churn.add_row(filepath, str(count))
        console.print(churn)
        console.print()

    # Drift indicators
    if report.drift_indicators:
        console.print("[bold]Drift Indicators[/bold]")
        for ind in report.drift_indicators:
            color = _SEVERITY_COLORS.get(ind.severity, "white")
            console.print(f"  [{color}]{ind.severity.upper()}[/{color}] {ind.description}")
        console.print()

    # Recommendations
    if report.recommendations:
        console.print("[bold]Recommendations[/bold]")
        for rec in report.recommendations:
            console.print(f"  - {rec}")
        console.print()
