"""Fetch command."""

import sys

import rich_click as click

from ..db import get_accounts, get_connection, init_db
from ._console import console
from ._helpers import _normalize_status_id_or_url
from ._progress import RichProgressReporter, create_progress, make_callbacks


@click.command()
@click.argument("status_id_or_url", required=False)
@click.option("--source", type=click.Choice(["home", "user", "search"]), default="home")
@click.option("--handle", "-u", help="User handle for user source")
@click.option("--query", "-q", help="Search query for search source")
@click.option("--count", "-n", default=200, help="Number of tweets to fetch")
@click.option("--tier1/--no-tier1", default=True, help="Also fetch tier-1 accounts")
@click.option("--bookmarks/--no-bookmarks", default=True, help="Also fetch bookmarks")
@click.option("--delay", type=float, default=None, help="Delay between tier-1 fetches (default: 3s)")
@click.option(
    "--stagger", type=int, default=None, help="Only fetch N tier-1 accounts (rotates by least-recently-fetched)"
)
def fetch(
    status_id_or_url: str | None,
    source: str,
    handle: str | None,
    query: str | None,
    count: int,
    tier1: bool,
    bookmarks: bool,
    delay: float | None,
    stagger: int | None,
):
    """Fetch tweets from Twitter/X."""
    from ..fetcher import fetch_bookmarks, fetch_home_timeline, fetch_search, fetch_user_tweets, read_tweet
    from ..processor import auto_promote_bookmarked_authors, store_bookmarked_tweets, store_fetched_tweets

    init_db()
    errors: list[str] = []

    if status_id_or_url:
        normalized = _normalize_status_id_or_url(status_id_or_url)
        console.print(f"Fetching status {normalized}...")
        tweet = read_tweet(status_id_or_url)
        if not tweet:
            raise click.ClickException(f"Status not found or unreadable: {normalized}")

        with create_progress() as progress:
            task_id = progress.add_task("Storing status", total=1)
            reporter = RichProgressReporter(progress, task_id, "Storing status")
            reporter.set_total(1)
            status_cb, progress_cb, _ = make_callbacks(reporter)
            fetched, new = store_fetched_tweets(
                [tweet],
                source="status",
                query_params={"status_id_or_url": status_id_or_url},
                status_cb=status_cb,
                progress_cb=progress_cb,
            )
        console.print(f"Fetched {fetched} tweets, {new} new")
        return

    console.print(f"Fetching from {source}...")

    if source == "user" and not handle:
        raise click.UsageError("--handle required for user source")
    if source == "search" and not query:
        raise click.UsageError("--query required for search source")

    # Main source fetch
    try:
        if source == "home":
            tweets = fetch_home_timeline(count=count)
        elif source == "user" and handle:
            tweets = fetch_user_tweets(handle=handle, count=count)
        else:
            tweets = fetch_search(query=query or "", count=count)

        if not tweets:
            fetched, new = 0, 0
        else:
            with create_progress() as progress:
                task_id = progress.add_task("Storing tweets", total=len(tweets))
                reporter = RichProgressReporter(progress, task_id, "Storing tweets")
                reporter.set_total(len(tweets))
                status_cb, progress_cb, _ = make_callbacks(reporter)

                fetched, new = store_fetched_tweets(
                    tweets,
                    source=source,
                    query_params={"handle": handle, "query": query, "count": count},
                    status_cb=status_cb,
                    progress_cb=progress_cb,
                )
        console.print(f"Fetched {fetched} tweets, {new} new")
    except RuntimeError as e:
        console.print(f"[red]Fetch failed: {e}[/red]")
        errors.append(str(e))

    # Fetch bookmarks
    if bookmarks and source == "home":
        console.print("Fetching bookmarks...")
        try:
            bm_tweets = fetch_bookmarks(count=100)
            if not bm_tweets:
                console.print("Bookmarks: 0 fetched, 0 new")
            else:
                with create_progress() as progress:
                    task_id = progress.add_task("Storing bookmarks", total=len(bm_tweets))
                    reporter = RichProgressReporter(progress, task_id, "Storing bookmarks")
                    reporter.set_total(len(bm_tweets))
                    status_cb, progress_cb, _ = make_callbacks(reporter)

                    bm_fetched, bm_new = store_bookmarked_tweets(
                        bm_tweets,
                        status_cb=status_cb,
                        progress_cb=progress_cb,
                    )
                console.print(f"Bookmarks: {bm_fetched} fetched, {bm_new} new")

            # Auto-promote authors with 3+ bookmarks
            promoted = auto_promote_bookmarked_authors(min_bookmarks=3)
            if promoted:
                console.print(f"Auto-promoted to tier-1: {', '.join('@' + h for h in promoted)}")
        except RuntimeError as e:
            console.print(f"[red]Bookmarks failed: {e}[/red]")
            errors.append(f"bookmarks: {e}")

    # Fetch tier-1 accounts if requested
    if tier1 and source == "home":
        import time

        from ..config import load_config
        from ..db import update_account_last_fetched

        cfg = load_config()
        fetch_delay = delay if delay is not None else cfg.get("fetch", {}).get("tier1_delay", 3)
        stagger_count = stagger if stagger is not None else cfg.get("fetch", {}).get("tier1_stagger")

        with get_connection() as conn:
            if stagger_count:
                tier1_accounts = get_accounts(conn, tier=1, limit=stagger_count, order_by_last_fetched=True)
            else:
                tier1_accounts = get_accounts(conn, tier=1)

        if tier1_accounts:
            if stagger_count:
                console.print(f"Fetching {len(tier1_accounts)} tier-1 accounts (staggered, delay: {fetch_delay}s)...")
            else:
                console.print(f"Fetching {len(tier1_accounts)} tier-1 accounts (delay: {fetch_delay}s)...")

            total_fetched = 0
            total_new = 0
            tier1_errors = 0

            for i, account in enumerate(tier1_accounts):
                try:
                    account_tweets = fetch_user_tweets(handle=account["handle"], count=20)
                    if account_tweets:
                        with create_progress() as progress:
                            task_id = progress.add_task(
                                f"  @{account['handle']}",
                                total=len(account_tweets),
                            )
                            reporter = RichProgressReporter(progress, task_id, f"  @{account['handle']}")
                            reporter.set_total(len(account_tweets))
                            status_cb, progress_cb, _ = make_callbacks(reporter)

                            f, n = store_fetched_tweets(
                                account_tweets,
                                source="user",
                                query_params={"handle": account["handle"], "count": 20},
                                status_cb=status_cb,
                                progress_cb=progress_cb,
                            )
                    else:
                        f, n = 0, 0
                    total_fetched += f
                    total_new += n

                    with get_connection() as conn:
                        update_account_last_fetched(conn, account["handle"])
                        conn.commit()

                except RuntimeError as e:
                    console.print(f"[red]  @{account['handle']}: {e}[/red]")
                    tier1_errors += 1

                # Rate limit protection
                if i < len(tier1_accounts) - 1 and fetch_delay > 0:
                    time.sleep(fetch_delay)

            console.print(f"Tier-1: fetched {total_fetched} tweets, {total_new} new")
            if tier1_errors:
                console.print(f"[red]Tier-1: {tier1_errors} account(s) failed[/red]")
                errors.append(f"tier-1: {tier1_errors} failed")

    if errors:
        console.print(f"\n[red]{len(errors)} error(s) during fetch[/red]")
        sys.exit(1)
