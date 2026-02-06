"""Digest command."""

from datetime import datetime

import rich_click as click

from ..db import init_db
from ._console import console


@click.command()
@click.option("--date", "-d", help="Date to generate digest for (YYYY-MM-DD)")
@click.option("--stdout", is_flag=True, help="Output to stdout instead of file")
@click.option("--min-score", type=float, help="Minimum score for inclusion")
def digest(date: str | None, stdout: bool, min_score: float | None):
    """Generate daily digest markdown."""
    from ..renderer import get_digest_path, render_digest

    init_db()
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    console.print(f"Generating digest for {date}...")

    output_path = None if stdout else get_digest_path(date)

    content = render_digest(
        date=date,
        min_score=min_score,
        output_path=output_path,
    )

    if stdout:
        click.echo(content)
    else:
        console.print(f"Written to: {output_path}")
