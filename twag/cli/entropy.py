"""CLI command for roadmap entropy detection."""

from __future__ import annotations

import json

import rich_click as click

from ._console import console


@click.command()
@click.option("--days", "-d", type=int, default=30, help="Look-back window in days.")
@click.option(
    "--format",
    "-f",
    "fmt",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format.",
)
@click.option(
    "--roadmap-file",
    type=click.Path(),
    default=".roadmap.yml",
    help="Path to roadmap YAML with focus-area weights.",
)
def entropy(days: int, fmt: str, roadmap_file: str) -> None:
    """Detect roadmap scope creep and drift from git history."""
    from ..entropy import (
        build_report,
        detect_drift,
        format_text_report,
        load_roadmap,
        parse_git_log,
    )

    roadmap = load_roadmap(roadmap_file)
    commits = parse_git_log(days=days)
    signals = detect_drift(commits, roadmap_weights=roadmap)
    report = build_report(commits, signals, roadmap_weights=roadmap, days=days)

    if fmt == "json":
        console.print_json(json.dumps(report))
    else:
        text = format_text_report(report)
        console.print(text)

    if signals:
        raise SystemExit(1)
