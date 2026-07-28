"""Spine signal-emission commands."""

import rich_click as click

from ..db import get_connection, init_db
from ..spine import emit_signals


@click.group()
def spine():
    """Emit scored signals to the shared spine ledger."""


@spine.command("emit")
def emit():
    """Append eligible processed tweets as signal-event v1 records."""
    init_db()
    with get_connection() as conn:
        events = emit_signals(conn)
    click.echo(f"Emitted {len(events)} signal event(s).")
