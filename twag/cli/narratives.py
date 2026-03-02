"""Narrative commands."""

import rich_click as click
from rich.table import Table

from ..db import get_active_narratives, get_connection
from ._console import console


@click.group()
def narratives():
    """Manage emerging narratives."""


@narratives.command("list")
def narratives_list():
    """List active narratives."""
    with get_connection(readonly=True) as conn:
        narrs = get_active_narratives(conn)

    if not narrs:
        console.print("No active narratives.")
        return

    table = Table(show_header=True)
    table.add_column("ID", justify="right")
    table.add_column("Name")
    table.add_column("Count", justify="right")
    table.add_column("Sentiment")

    for n in narrs:
        sentiment = n["sentiment"] or "-"
        table.add_row(str(n["id"]), n["name"], str(n["mention_count"]), sentiment)

    console.print(table)
