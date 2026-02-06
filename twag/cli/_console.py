"""Shared Rich console instance and helpers."""

from rich.console import Console

console = Console()


def status_icon(ok: bool) -> str:
    """Return a colored checkmark or cross for status output."""
    if ok:
        return "[green]\u2713[/green]"
    return "[red]\u2717[/red]"
