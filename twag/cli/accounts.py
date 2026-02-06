"""Account management commands."""

import sys

import rich_click as click
from rich.table import Table

from ..config import get_following_path
from ..db import (
    apply_account_decay,
    boost_account,
    get_accounts,
    get_connection,
    mute_account,
    promote_account,
    upsert_account,
)
from ._console import console


@click.group()
def accounts():
    """Manage tracked accounts."""
    pass


@accounts.command("list")
@click.option("--tier", "-t", type=int, help="Filter by tier")
@click.option("--muted", is_flag=True, help="Include muted accounts")
def accounts_list(tier: int | None, muted: bool):
    """List tracked accounts."""
    with get_connection(readonly=True) as conn:
        accts = get_accounts(conn, tier=tier, include_muted=muted)

    if not accts:
        console.print("No accounts found.")
        return

    table = Table(show_header=True)
    table.add_column("Handle", style="cyan")
    table.add_column("Tier", justify="right")
    table.add_column("Weight", justify="right")
    table.add_column("Seen", justify="right")
    table.add_column("Kept", justify="right")
    table.add_column("Avg", justify="right")

    for a in accts:
        avg = f"{a['avg_relevance_score']:.1f}" if a["avg_relevance_score"] else "-"
        weight_style = "green" if a["weight"] >= 1.0 else "yellow" if a["weight"] >= 0.5 else "red"
        table.add_row(
            f"@{a['handle']}",
            str(a["tier"]),
            f"[{weight_style}]{a['weight']:.1f}[/{weight_style}]",
            str(a["tweets_seen"]),
            str(a["tweets_kept"]),
            avg,
        )

    console.print(table)


@accounts.command("add")
@click.argument("handle")
@click.option("--tier", "-t", type=int, default=2, help="Account tier (1=core, 2=followed)")
@click.option("--category", "-c", help="Account category")
def accounts_add(handle: str, tier: int, category: str | None):
    """Add an account to tracking."""
    with get_connection() as conn:
        upsert_account(conn, handle, tier=tier, category=category)
        conn.commit()
    console.print(f"Added @{handle.lstrip('@')} as tier {tier}")


@accounts.command("promote")
@click.argument("handle")
def accounts_promote(handle: str):
    """Promote an account to tier 1."""
    with get_connection() as conn:
        promote_account(conn, handle)
        conn.commit()
    console.print(f"Promoted @{handle.lstrip('@')} to tier 1")


@accounts.command("mute")
@click.argument("handle")
def accounts_mute(handle: str):
    """Mute an account (stop tracking)."""
    with get_connection() as conn:
        mute_account(conn, handle)
        conn.commit()
    console.print(f"Muted @{handle.lstrip('@')}")


@accounts.command("demote")
@click.argument("handle")
@click.option("--tier", "-t", type=int, default=2, help="Tier to demote to (default: 2)")
def accounts_demote(handle: str, tier: int):
    """Demote an account from tier 1."""
    from ..db import demote_account

    with get_connection() as conn:
        demote_account(conn, handle, tier=tier)
        conn.commit()
    console.print(f"Demoted @{handle.lstrip('@')} to tier {tier}")


@accounts.command("decay")
@click.option("--rate", type=float, default=0.05, help="Decay rate (0-1)")
def accounts_decay(rate: float):
    """Apply daily decay to account weights."""
    with get_connection() as conn:
        affected = apply_account_decay(conn, decay_rate=rate)
        conn.commit()
    console.print(f"Applied {rate * 100:.0f}% decay to {affected} accounts")


@accounts.command("boost")
@click.argument("handle")
@click.option("--amount", type=float, default=5.0, help="Boost amount")
def accounts_boost(handle: str, amount: float):
    """Boost an account's weight."""
    with get_connection() as conn:
        boost_account(conn, handle, amount=amount)
        conn.commit()
    console.print(f"Boosted @{handle.lstrip('@')} by {amount}")


@accounts.command("import")
@click.option("--tier", "-t", type=int, default=2, help="Default tier for imported accounts")
def accounts_import(tier: int):
    """Import accounts from following.txt."""
    following_path = get_following_path()

    if not following_path.exists():
        console.print(f"[red]No following file at: {following_path}[/red]")
        sys.exit(1)

    with open(following_path) as f:
        handles = [line.strip().lstrip("@") for line in f if line.strip() and not line.startswith("#")]

    console.print(f"Importing {len(handles)} accounts...")

    with get_connection() as conn:
        for handle in handles:
            if handle:
                upsert_account(conn, handle, tier=tier)
        conn.commit()

    console.print(f"Imported {len(handles)} accounts as tier {tier}")
