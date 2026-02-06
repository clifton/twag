"""CLI entry point for twag."""

import json
import re
import shutil
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import click

from . import __version__
from .article_sections import parse_action_items, parse_primary_points
from .article_visuals import build_article_visuals
from .config import (
    get_config_path,
    get_data_dir,
    get_database_path,
    get_digests_dir,
    get_following_path,
    load_config,
    save_config,
)
from .db import (
    apply_account_decay,
    archive_stale_narratives,
    boost_account,
    dump_sql,
    get_accounts,
    get_active_narratives,
    get_connection,
    get_processed_counts,
    get_tweet_by_id,
    get_tweet_stats,
    get_unprocessed_tweets,
    init_db,
    mute_account,
    parse_time_range,
    promote_account,
    prune_old_tweets,
    query_suggests_equity_context,
    rebuild_fts,
    restore_sql,
    search_tweets,
    upsert_account,
)


def _make_progress_callbacks(bar: click.progressbar, total: int, base_label: str):
    state = {"count": 0, "total": max(0, total), "label": base_label}

    def _format(label: str) -> str:
        return f"{label} ({state['count']}/{state['total']})"

    def _sync_label() -> None:
        bar.label = _format(state["label"])
        bar.update(0)

    try:
        bar.length = state["total"]
    except Exception:
        pass
    _sync_label()

    def status_cb(msg: str) -> None:
        state["label"] = msg
        _sync_label()

    def progress_cb(step: int = 1) -> None:
        if step < 0:
            step = 0
        state["count"] = min(state["total"], state["count"] + step)
        _sync_label()
        bar.update(step)

    def total_cb(new_total: int) -> None:
        if new_total < state["count"]:
            new_total = state["count"]
        state["total"] = new_total
        try:
            bar.length = new_total
        except Exception:
            pass
        _sync_label()

    return status_cb, progress_cb, total_cb


def _normalize_status_id_or_url(status_id_or_url: str) -> str:
    """Normalize a status argument to a tweet ID when possible."""
    value = status_id_or_url.strip()
    if value.isdigit():
        return value

    match = re.search(r"/status/(\d+)", value)
    if match:
        return match.group(1)

    return value


def _json_list(value: str | None) -> list:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return decoded if isinstance(decoded, list) else []


def _json_object(value: str | None) -> dict:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _analysis_wrap_width() -> int:
    """Best-effort terminal width for long-form analyze output."""
    try:
        columns = shutil.get_terminal_size(fallback=(110, 20)).columns
    except OSError:
        columns = 110
    return max(78, min(columns, 132))


def _echo_wrapped(text: str, *, initial_indent: str = "", subsequent_indent: str | None = None) -> None:
    cleaned = str(text or "").strip()
    if not cleaned:
        return
    if subsequent_indent is None:
        subsequent_indent = initial_indent
    click.echo(
        textwrap.fill(
            cleaned,
            width=_analysis_wrap_width(),
            initial_indent=initial_indent,
            subsequent_indent=subsequent_indent,
            break_long_words=False,
            break_on_hyphens=False,
        )
    )


def _echo_labeled(label: str, value: str, *, indent: str = "   ") -> None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return
    prefix = f"{indent}{label}: "
    _echo_wrapped(cleaned, initial_indent=prefix, subsequent_indent=" " * len(prefix))


def _print_status_analysis(row) -> None:
    score = row["relevance_score"] if row["relevance_score"] is not None else 0.0
    categories = _json_list(row["category"])
    tickers = _json_list(row["tickers"])

    click.echo("")
    click.echo(f"@{row['author_handle']} · {row['id']}")
    click.echo(f"Score: {score:.1f} · Tier: {row['signal_tier'] or '-'}")
    if categories:
        click.echo(f"Categories: {', '.join(str(c) for c in categories)}")
    if tickers:
        click.echo(f"Tickers: {', '.join(str(t) for t in tickers)}")

    summary = row["summary"] or row["content_summary"] or ""
    if summary:
        click.echo("")
        click.echo("Summary:")
        _echo_wrapped(summary, initial_indent="  ")

    article_summary = row["article_summary_short"] or ""
    primary_points = parse_primary_points(row["article_primary_points_json"])
    actionable_items = parse_action_items(row["article_action_items_json"])
    top_visual = _json_object(row["article_top_visual_json"])
    media_items = [item for item in _json_list(row["media_items"]) if isinstance(item, dict)]

    if article_summary:
        click.echo("")
        click.echo("Article Summary:")
        _echo_wrapped(article_summary, initial_indent="- ", subsequent_indent="  ")

    if primary_points:
        click.echo("")
        click.echo("Primary Points:")
        for idx, point in enumerate(primary_points, start=1):
            main = point["point"]
            reasoning = point["reasoning"]
            evidence = point["evidence"]
            _echo_wrapped(main, initial_indent=f"{idx}. ", subsequent_indent=" " * (len(str(idx)) + 2))
            _echo_labeled("Why", reasoning)
            _echo_labeled("Evidence", evidence)

    if actionable_items:
        click.echo("")
        click.echo("Actionable Items:")
        for idx, item in enumerate(actionable_items, start=1):
            _echo_wrapped(item["action"], initial_indent=f"{idx}. ", subsequent_indent=" " * (len(str(idx)) + 2))
            _echo_labeled("Trigger", item["trigger"])
            _echo_labeled("Horizon", item["horizon"])
            _echo_labeled("Confidence", item["confidence"])
            _echo_labeled("Tickers", item["tickers"])

    visuals = build_article_visuals(top_visual=top_visual or None, media_items=media_items, max_items=5)
    if visuals:
        click.echo("")
        click.echo("Visuals:")
        for idx, visual in enumerate(visuals, start=1):
            url = str(visual.get("url") or "").strip()
            kind = str(visual.get("kind") or "visual").strip()
            why_important = str(visual.get("why_important") or "").strip()
            key_takeaway = str(visual.get("key_takeaway") or "").strip()
            top_prefix = " (top)" if visual.get("is_top") else ""
            click.echo(f"{idx}. {kind}{top_prefix}")
            _echo_labeled("Key takeaway", key_takeaway)
            _echo_labeled("Why", why_important)
            _echo_labeled("URL", url)

    if not article_summary and row["link_summary"]:
        click.echo("")
        click.echo("Linked Summary:")
        _echo_wrapped(str(row["link_summary"]), initial_indent="- ", subsequent_indent="  ")


@click.group()
@click.version_option(version=__version__)
def cli():
    """Twitter aggregator for market-relevant signals."""
    pass


# ============================================================================
# Init and Doctor commands
# ============================================================================


@cli.command()
@click.option("--force", is_flag=True, help="Overwrite existing config file")
def init(force: bool):
    """Initialize twag data directories and configuration.

    Creates:
    - Data directory (~/.local/share/twag/ or TWAG_DATA_DIR)
    - Config file (~/.config/twag/config.json)
    - Database (twag.db)
    - Digests directory
    """

    data_dir = get_data_dir()
    config_path = get_config_path()
    db_path = get_database_path()
    digests_dir = get_digests_dir()
    following_path = get_following_path()

    click.echo("Initializing twag...")
    click.echo(f"  Data directory: {data_dir}")
    click.echo(f"  Config file: {config_path}")

    # Create data directory
    data_dir.mkdir(parents=True, exist_ok=True)
    click.echo("  [OK] Data directory created")

    # Create digests directory
    digests_dir.mkdir(parents=True, exist_ok=True)
    click.echo("  [OK] Digests directory created")

    # Create config file
    if config_path.exists() and not force:
        click.echo("  [SKIP] Config already exists (use --force to overwrite)")
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        save_config(load_config())
        click.echo("  [OK] Config file created")

    # Initialize database
    init_db()
    click.echo(f"  [OK] Database initialized at {db_path}")

    # Create empty following.txt if it doesn't exist
    if not following_path.exists():
        following_path.write_text("# Add Twitter handles to track (one per line)\n# Example: @NickTimiraos\n")
        click.echo(f"  [OK] Following file created at {following_path}")
    else:
        click.echo("  [SKIP] Following file already exists")

    click.echo("")
    click.echo("Initialization complete! Next steps:")
    click.echo("  1. Set API keys: export GEMINI_API_KEY=... ANTHROPIC_API_KEY=...")
    click.echo("  2. Set Twitter auth: export AUTH_TOKEN=... CT0=...")
    click.echo("  3. Run: twag doctor")
    click.echo("  4. Add accounts: twag accounts add @handle")
    click.echo("  5. Fetch tweets: twag fetch")


@cli.command()
def doctor():
    """Check twag dependencies and configuration.

    Verifies:
    - Required directories exist
    - Config file is valid
    - API keys are set
    - bird CLI is available
    - Database is accessible
    """
    import os
    import shutil

    issues = []
    warnings = []

    click.echo("Checking twag configuration...\n")

    # 1. Check data directory
    data_dir = get_data_dir()
    click.echo(f"Data directory: {data_dir}")
    if data_dir.exists():
        click.echo("  [OK] Directory exists")
    else:
        click.echo("  [ERROR] Directory does not exist")
        issues.append("Run 'twag init' to create data directory")

    # 2. Check config file
    config_path = get_config_path()
    click.echo(f"\nConfig file: {config_path}")
    if config_path.exists():
        try:
            load_config()
            click.echo("  [OK] Config file valid")
        except Exception as e:
            click.echo(f"  [ERROR] Config file invalid: {e}")
            issues.append("Fix or delete config file")
    else:
        click.echo("  [WARN] Config file not found (using defaults)")
        warnings.append("Run 'twag init' to create config file")

    # 3. Check database
    db_path = get_database_path()
    click.echo(f"\nDatabase: {db_path}")
    if db_path.exists():
        try:
            with get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM tweets")
                count = cursor.fetchone()[0]
            click.echo(f"  [OK] Database accessible ({count} tweets)")
        except Exception as e:
            click.echo(f"  [ERROR] Database error: {e}")
            issues.append("Run 'twag db init' to repair database")
    else:
        click.echo("  [WARN] Database not found")
        warnings.append("Run 'twag init' to create database")

    # 4. Check bird CLI
    click.echo("\nbird CLI:")
    bird_path = shutil.which("bird")
    if bird_path:
        click.echo(f"  [OK] Found at {bird_path}")
    else:
        click.echo("  [ERROR] bird CLI not found in PATH")
        issues.append("Install bird CLI: cargo install bird-cli or see https://github.com/...")

    # 5. Check API keys
    click.echo("\nAPI keys:")

    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        click.echo(f"  [OK] GEMINI_API_KEY set ({gemini_key[:8]}...)")
    else:
        click.echo("  [ERROR] GEMINI_API_KEY not set")
        issues.append("Set GEMINI_API_KEY environment variable")

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        click.echo(f"  [OK] ANTHROPIC_API_KEY set ({anthropic_key[:8]}...)")
    else:
        click.echo("  [WARN] ANTHROPIC_API_KEY not set (enrichment disabled)")
        warnings.append("Set ANTHROPIC_API_KEY for enrichment features")

    # 6. Check Twitter auth
    click.echo("\nTwitter auth:")
    auth_token = os.environ.get("AUTH_TOKEN")
    ct0 = os.environ.get("CT0")

    if auth_token:
        click.echo("  [OK] AUTH_TOKEN set")
    else:
        click.echo("  [ERROR] AUTH_TOKEN not set")
        issues.append("Set AUTH_TOKEN environment variable")

    if ct0:
        click.echo("  [OK] CT0 set")
    else:
        click.echo("  [ERROR] CT0 not set")
        issues.append("Set CT0 environment variable")

    # 7. Check Telegram (optional)
    click.echo("\nTelegram notifications:")
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID")

    if telegram_token and telegram_chat:
        click.echo("  [OK] Telegram configured")
    elif telegram_token or telegram_chat:
        click.echo("  [WARN] Partial Telegram config")
        warnings.append("Set both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    else:
        click.echo("  [INFO] Telegram not configured (optional)")

    # Summary
    click.echo("\n" + "=" * 50)

    if issues:
        click.echo(f"\n{len(issues)} issue(s) found:")
        for issue in issues:
            click.echo(f"  - {issue}")
        sys.exit(1)
    elif warnings:
        click.echo(f"\nAll checks passed with {len(warnings)} warning(s):")
        for warning in warnings:
            click.echo(f"  - {warning}")
    else:
        click.echo("\nAll checks passed!")


# ============================================================================
# Fetch commands
# ============================================================================


@cli.command()
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
    from .fetcher import fetch_bookmarks, fetch_home_timeline, fetch_search, fetch_user_tweets, read_tweet
    from .processor import auto_promote_bookmarked_authors, store_bookmarked_tweets, store_fetched_tweets

    init_db()

    if status_id_or_url:
        click.echo(f"Fetching status {status_id_or_url}...")
        tweet = read_tweet(status_id_or_url)
        if not tweet:
            raise click.ClickException(f"Status not found or unreadable: {status_id_or_url}")

        with click.progressbar(length=1, label="Storing status") as bar:
            status_cb, progress_cb, _ = _make_progress_callbacks(bar, 1, "Storing status")
            fetched, new = store_fetched_tweets(
                [tweet],
                source="status",
                query_params={"status_id_or_url": status_id_or_url},
                status_cb=status_cb,
                progress_cb=progress_cb,
            )
        click.echo(f"Fetched {fetched} tweets, {new} new")
        return

    click.echo(f"Fetching from {source}...")

    if source == "user" and not handle:
        raise click.UsageError("--handle required for user source")
    if source == "search" and not query:
        raise click.UsageError("--query required for search source")

    try:
        if source == "home":
            tweets = fetch_home_timeline(count=count)
        elif source == "user" and handle:
            tweets = fetch_user_tweets(handle=handle, count=count)
        else:
            tweets = fetch_search(query=query or "", count=count)

        if not tweets:
            click.echo("Fetched 0 tweets.")
            fetched, new = 0, 0
        else:
            with click.progressbar(length=len(tweets), label="Storing tweets") as bar:
                status_cb, progress_cb, _ = _make_progress_callbacks(bar, len(tweets), "Storing tweets")

                fetched, new = store_fetched_tweets(
                    tweets,
                    source=source,
                    query_params={"handle": handle, "query": query, "count": count},
                    status_cb=status_cb,
                    progress_cb=progress_cb,
                )
        click.echo(f"Fetched {fetched} tweets, {new} new")

        # Fetch bookmarks
        if bookmarks and source == "home":
            click.echo("Fetching bookmarks...")
            try:
                bm_tweets = fetch_bookmarks(count=100)
                if not bm_tweets:
                    click.echo("Bookmarks: 0 fetched, 0 new")
                else:
                    with click.progressbar(length=len(bm_tweets), label="Storing bookmarks") as bar:
                        status_cb, progress_cb, _ = _make_progress_callbacks(bar, len(bm_tweets), "Storing bookmarks")

                        bm_fetched, bm_new = store_bookmarked_tweets(
                            bm_tweets,
                            status_cb=status_cb,
                            progress_cb=progress_cb,
                        )
                    click.echo(f"Bookmarks: {bm_fetched} fetched, {bm_new} new")

                # Auto-promote authors with 3+ bookmarks
                promoted = auto_promote_bookmarked_authors(min_bookmarks=3)
                if promoted:
                    click.echo(f"Auto-promoted to tier-1: {', '.join('@' + h for h in promoted)}")
            except Exception as e:
                click.echo(f"Bookmarks failed: {e}", err=True)

        # Fetch tier-1 accounts if requested
        if tier1 and source == "home":
            import time

            from .config import load_config
            from .db import update_account_last_fetched

            cfg = load_config()
            fetch_delay = delay if delay is not None else cfg.get("fetch", {}).get("tier1_delay", 3)
            stagger_count = stagger if stagger is not None else cfg.get("fetch", {}).get("tier1_stagger")

            with get_connection() as conn:
                # If staggering, get least-recently-fetched accounts
                if stagger_count:
                    tier1_accounts = get_accounts(conn, tier=1, limit=stagger_count, order_by_last_fetched=True)
                else:
                    tier1_accounts = get_accounts(conn, tier=1)

            if tier1_accounts:
                if stagger_count:
                    click.echo(f"Fetching {len(tier1_accounts)} tier-1 accounts (staggered, delay: {fetch_delay}s)...")
                else:
                    click.echo(f"Fetching {len(tier1_accounts)} tier-1 accounts (delay: {fetch_delay}s)...")

                total_fetched = 0
                total_new = 0

                for i, account in enumerate(tier1_accounts):
                    try:
                        account_tweets = fetch_user_tweets(handle=account["handle"], count=20)
                        if account_tweets:
                            with click.progressbar(
                                length=len(account_tweets), label=f"Storing @{account['handle']}"
                            ) as bar:
                                status_cb, progress_cb, _ = _make_progress_callbacks(
                                    bar,
                                    len(account_tweets),
                                    f"Storing @{account['handle']}",
                                )

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

                        # Update last fetched timestamp
                        with get_connection() as conn:
                            update_account_last_fetched(conn, account["handle"])
                            conn.commit()

                    except Exception as e:
                        click.echo(f"  @{account['handle']}: failed ({e})", err=True)

                    # Rate limit protection
                    if i < len(tier1_accounts) - 1 and fetch_delay > 0:
                        time.sleep(fetch_delay)

                click.echo(f"Tier-1: fetched {total_fetched} tweets, {total_new} new")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# Process commands
# ============================================================================


@cli.command()
@click.argument("status_id_or_url", required=False)
@click.option("--limit", "-n", default=250, help="Max tweets to process")
@click.option("--dry-run", is_flag=True, help="Show what would be processed")
@click.option("--model", "-m", help="Override triage model")
@click.option("--notify/--no-notify", default=True, help="Send Telegram alerts")
@click.option("--reprocess-quotes/--no-reprocess-quotes", default=True, help="Reprocess today's quoted tweets")
@click.option("--reprocess-min-score", type=float, default=None, help="Min score for reprocessing quoted tweets")
def process(
    status_id_or_url: str | None,
    limit: int,
    dry_run: bool,
    model: str | None,
    notify: bool,
    reprocess_quotes: bool,
    reprocess_min_score: float | None,
):
    """Process unscored tweets through LLM."""
    from .notifier import notify_high_signal_tweet
    from .processor import process_unprocessed, reprocess_today_quoted

    init_db()

    target_tweet_id = _normalize_status_id_or_url(status_id_or_url) if status_id_or_url else None
    if target_tweet_id:
        click.echo(f"Processing status {target_tweet_id}...")
    else:
        click.echo(f"Processing up to {limit} tweets...")

    if dry_run:
        click.echo("(dry run - no changes will be made)")

    with get_connection() as conn:
        if target_tweet_id:
            target_row = get_tweet_by_id(conn, target_tweet_id)
            if not target_row:
                raise click.ClickException(
                    f"Status not found in database: {target_tweet_id}. Fetch it first with `twag fetch {target_tweet_id}`."
                )
            unprocessed_rows = [target_row]
        else:
            unprocessed_rows = get_unprocessed_tweets(conn, limit=limit)

    if unprocessed_rows:
        with click.progressbar(length=len(unprocessed_rows), label="Processing tweets") as bar:
            status_cb, progress_cb, total_cb = _make_progress_callbacks(bar, len(unprocessed_rows), "Processing tweets")

            results = process_unprocessed(
                limit=limit,
                dry_run=dry_run,
                triage_model=model,
                rows=unprocessed_rows,
                progress_cb=progress_cb,
                status_cb=status_cb,
                total_cb=total_cb,
            )
    else:
        results = []

    if not results:
        click.echo("No unprocessed tweets found.")
    else:
        # Show results
        high_signal = [r for r in results if r.score >= 8]
        market_relevant = [r for r in results if 6 <= r.score < 8]

        click.echo(f"Processed {len(results)} tweets:")
        click.echo(f"  High signal: {len(high_signal)}")
        click.echo(f"  Market relevant: {len(market_relevant)}")

        # Show high signal tweets
        if high_signal:
            click.echo("\n🔥 High Signal:")
            for r in high_signal[:5]:
                click.echo(f"  [{r.score:.1f}] {', '.join(r.categories)}: {r.summary[:60]}")

                # Send notification if enabled
                if notify and not dry_run:
                    # Get tweet content from DB
                    with get_connection() as conn:
                        cursor = conn.execute(
                            "SELECT content, author_handle FROM tweets WHERE id = ?",
                            (r.tweet_id,),
                        )
                        row = cursor.fetchone()
                        if row:
                            notify_high_signal_tweet(
                                tweet_id=r.tweet_id,
                                author_handle=row["author_handle"],
                                content=row["content"],
                                score=r.score,
                                category=r.categories,
                                summary=r.summary,
                                tickers=r.tickers,
                            )

    if target_tweet_id and reprocess_quotes:
        click.echo("Skipping quote reprocessing for single-status mode.")
        reprocess_quotes = False

    if reprocess_quotes:
        cfg = load_config()
        min_score = (
            reprocess_min_score if reprocess_min_score is not None else cfg["scoring"].get("min_score_for_reprocess", 3)
        )
        reprocess_limit = 200
        today = datetime.now().strftime("%Y-%m-%d")

        with get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM tweets
                WHERE processed_at IS NOT NULL
                  AND has_quote = 1
                  AND quote_tweet_id IS NOT NULL
                  AND date(created_at) = ?
                  AND relevance_score >= ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (today, min_score, reprocess_limit),
            )
            quote_rows = cursor.fetchall()

        click.echo("Reprocessing today's quoted tweets...")
        if quote_rows:
            with click.progressbar(length=len(quote_rows), label="Reprocessing quoted") as bar:
                status_cb, progress_cb, _ = _make_progress_callbacks(bar, len(quote_rows), "Reprocessing quoted")

                reprocessed = reprocess_today_quoted(
                    limit=reprocess_limit,
                    dry_run=dry_run,
                    triage_model=model,
                    min_score=min_score,
                    rows=quote_rows,
                    progress_cb=progress_cb,
                    status_cb=status_cb,
                )
        else:
            reprocessed = []

        if reprocessed:
            click.echo(f"Reprocessed {len(reprocessed)} quoted tweets.")
        else:
            click.echo("No quoted tweets to reprocess.")


# ============================================================================
# Analyze commands
# ============================================================================


@cli.command()
@click.argument("status_id_or_url")
@click.option("--model", "-m", help="Override triage model")
@click.option("--reprocess/--no-reprocess", default=False, help="Reprocess even if already processed")
def analyze(status_id_or_url: str, model: str | None, reprocess: bool):
    """Fetch, process, and print structured analysis for one status."""
    from .fetcher import read_tweet
    from .processor import process_unprocessed, store_fetched_tweets

    init_db()
    normalized_id = _normalize_status_id_or_url(status_id_or_url)
    click.echo(f"Analyzing status {normalized_id}...")

    tweet = read_tweet(status_id_or_url)
    if not tweet:
        raise click.ClickException(f"Status not found or unreadable: {status_id_or_url}")

    with click.progressbar(length=1, label="Storing status") as bar:
        status_cb, progress_cb, _ = _make_progress_callbacks(bar, 1, "Storing status")
        fetched, new = store_fetched_tweets(
            [tweet],
            source="status",
            query_params={"status_id_or_url": status_id_or_url},
            status_cb=status_cb,
            progress_cb=progress_cb,
        )
    click.echo(f"Fetched {fetched} tweets, {new} new")

    with get_connection() as conn:
        row = get_tweet_by_id(conn, tweet.id) or get_tweet_by_id(conn, normalized_id)

    if not row:
        raise click.ClickException(f"Status not found in database after fetch: {normalized_id}")

    if row["processed_at"] and not reprocess:
        click.echo("Status already processed; using existing analysis (pass --reprocess to refresh).")
    else:
        with click.progressbar(length=1, label="Processing status") as bar:
            status_cb, progress_cb, total_cb = _make_progress_callbacks(bar, 1, "Processing status")
            process_unprocessed(
                limit=1,
                dry_run=False,
                triage_model=model,
                rows=[row],
                progress_cb=progress_cb,
                status_cb=status_cb,
                total_cb=total_cb,
                force_refresh=reprocess,
            )

    with get_connection() as conn:
        final_row = get_tweet_by_id(conn, tweet.id) or get_tweet_by_id(conn, normalized_id)

    if not final_row:
        raise click.ClickException(f"Unable to load processed status: {normalized_id}")

    _print_status_analysis(final_row)


# ============================================================================
# Digest commands
# ============================================================================


@cli.command()
@click.option("--date", "-d", help="Date to generate digest for (YYYY-MM-DD)")
@click.option("--stdout", is_flag=True, help="Output to stdout instead of file")
@click.option("--min-score", type=float, help="Minimum score for inclusion")
def digest(date: str | None, stdout: bool, min_score: float | None):
    """Generate daily digest markdown."""
    from .renderer import get_digest_path, render_digest

    init_db()
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    click.echo(f"Generating digest for {date}...")

    output_path = None if stdout else get_digest_path(date)

    content = render_digest(
        date=date,
        min_score=min_score,
        output_path=output_path,
    )

    if stdout:
        click.echo(content)
    else:
        click.echo(f"Written to: {output_path}")


# ============================================================================
# Account commands
# ============================================================================


@cli.group()
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
        click.echo("No accounts found.")
        return

    click.echo(f"{'Handle':<20} {'Tier':<5} {'Weight':<8} {'Seen':<6} {'Kept':<6} {'Avg':<6}")
    click.echo("-" * 60)

    for a in accts:
        avg = f"{a['avg_relevance_score']:.1f}" if a["avg_relevance_score"] else "-"
        click.echo(
            f"@{a['handle']:<19} {a['tier']:<5} {a['weight']:<8.1f} "
            f"{a['tweets_seen']:<6} {a['tweets_kept']:<6} {avg:<6}"
        )


@accounts.command("add")
@click.argument("handle")
@click.option("--tier", "-t", type=int, default=2, help="Account tier (1=core, 2=followed)")
@click.option("--category", "-c", help="Account category")
def accounts_add(handle: str, tier: int, category: str | None):
    """Add an account to tracking."""
    with get_connection() as conn:
        upsert_account(conn, handle, tier=tier, category=category)
        conn.commit()
    click.echo(f"Added @{handle.lstrip('@')} as tier {tier}")


@accounts.command("promote")
@click.argument("handle")
def accounts_promote(handle: str):
    """Promote an account to tier 1."""
    with get_connection() as conn:
        promote_account(conn, handle)
        conn.commit()
    click.echo(f"Promoted @{handle.lstrip('@')} to tier 1")


@accounts.command("mute")
@click.argument("handle")
def accounts_mute(handle: str):
    """Mute an account (stop tracking)."""
    with get_connection() as conn:
        mute_account(conn, handle)
        conn.commit()
    click.echo(f"Muted @{handle.lstrip('@')}")


@accounts.command("demote")
@click.argument("handle")
@click.option("--tier", "-t", type=int, default=2, help="Tier to demote to (default: 2)")
def accounts_demote(handle: str, tier: int):
    """Demote an account from tier 1."""
    from .db import demote_account

    with get_connection() as conn:
        demote_account(conn, handle, tier=tier)
        conn.commit()
    click.echo(f"Demoted @{handle.lstrip('@')} to tier {tier}")


@accounts.command("decay")
@click.option("--rate", type=float, default=0.05, help="Decay rate (0-1)")
def accounts_decay(rate: float):
    """Apply daily decay to account weights."""
    with get_connection() as conn:
        affected = apply_account_decay(conn, decay_rate=rate)
        conn.commit()
    click.echo(f"Applied {rate * 100:.0f}% decay to {affected} accounts")


@accounts.command("boost")
@click.argument("handle")
@click.option("--amount", type=float, default=5.0, help="Boost amount")
def accounts_boost(handle: str, amount: float):
    """Boost an account's weight."""
    with get_connection() as conn:
        boost_account(conn, handle, amount=amount)
        conn.commit()
    click.echo(f"Boosted @{handle.lstrip('@')} by {amount}")


@accounts.command("import")
@click.option("--tier", "-t", type=int, default=2, help="Default tier for imported accounts")
def accounts_import(tier: int):
    """Import accounts from following.txt."""
    following_path = get_following_path()

    if not following_path.exists():
        click.echo(f"No following file at: {following_path}", err=True)
        sys.exit(1)

    with open(following_path) as f:
        handles = [line.strip().lstrip("@") for line in f if line.strip() and not line.startswith("#")]

    click.echo(f"Importing {len(handles)} accounts...")

    with get_connection() as conn:
        for handle in handles:
            if handle:
                upsert_account(conn, handle, tier=tier)
        conn.commit()

    click.echo(f"Imported {len(handles)} accounts as tier {tier}")


# ============================================================================
# Narrative commands
# ============================================================================


@cli.group()
def narratives():
    """Manage emerging narratives."""
    pass


@narratives.command("list")
def narratives_list():
    """List active narratives."""
    with get_connection(readonly=True) as conn:
        narrs = get_active_narratives(conn)

    if not narrs:
        click.echo("No active narratives.")
        return

    click.echo(f"{'ID':<4} {'Name':<30} {'Count':<6} {'Sentiment':<10}")
    click.echo("-" * 55)

    for n in narrs:
        sentiment = n["sentiment"] or "-"
        click.echo(f"{n['id']:<4} {n['name']:<30} {n['mention_count']:<6} {sentiment:<10}")


# ============================================================================
# Stats and maintenance
# ============================================================================


@cli.command()
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
        click.echo("No tweets found.")
        return

    period = f"for {date}" if date else "all time"
    click.echo(f"Tweet statistics ({period}):")
    click.echo(f"  Total: {s['total']}")
    click.echo(f"  Processed: {s['processed']}")
    click.echo(f"  Pending: {s['pending']}")
    click.echo(f"  Avg score: {s['avg_score']:.1f}" if s["avg_score"] else "  Avg score: -")
    click.echo(f"  High signal (≥7): {s['high_signal']}")
    click.echo(f"  Digest worthy (≥5): {s['digest_worthy']}")

    # Show recent processing activity (only for all-time stats)
    if not date:
        click.echo("")
        click.echo("Recent processing:")
        click.echo(f"  Last 1h:  {recent['1h']} tweets")
        click.echo(f"  Last 24h: {recent['24h']} tweets")
        click.echo(f"  Last 7d:  {recent['7d']} tweets")


@cli.command()
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
            click.echo(f"Would delete {count} tweets older than {days} days")
        else:
            deleted = prune_old_tweets(conn, days=days)
            stale = archive_stale_narratives(conn, days=7)
            conn.commit()
            click.echo(f"Deleted {deleted} old tweets, archived {stale} stale narratives")


@cli.command()
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


# ============================================================================
# Config commands
# ============================================================================


@cli.group()
def config():
    """Manage configuration."""
    pass


@config.command("show")
def config_show():
    """Show current configuration."""
    cfg = load_config()
    click.echo(json.dumps(cfg, indent=2))


@config.command("path")
def config_path():
    """Show configuration file path."""
    click.echo(get_config_path())


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Set a configuration value (e.g., llm.model sonnet)."""
    cfg = load_config()

    # Parse key path
    parts = key.split(".")
    target = cfg
    for part in parts[:-1]:
        if part not in target:
            target[part] = {}
        target = target[part]

    # Parse value (try as JSON, fall back to string)
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    target[parts[-1]] = parsed_value
    save_config(cfg)
    click.echo(f"Set {key} = {parsed_value}")


# ============================================================================
# Database commands
# ============================================================================


@cli.group()
def db():
    """Database operations."""
    pass


@db.command("path")
def db_path():
    """Show database file path."""
    click.echo(get_database_path())


@db.command("shell")
def db_shell():
    """Open SQLite shell."""
    import subprocess

    db_file = get_database_path()
    subprocess.run(["sqlite3", str(db_file)])


@db.command("init")
def db_init():
    """Initialize/reset the database."""
    init_db()
    click.echo(f"Database initialized at: {get_database_path()}")


@db.command("rebuild-fts")
def db_rebuild_fts():
    """Rebuild the FTS5 full-text search index."""
    click.echo("Rebuilding FTS index...")
    with get_connection() as conn:
        count = rebuild_fts(conn)
        conn.commit()
    click.echo(f"Indexed {count} tweets")


@db.command("dump")
@click.argument("output", type=click.Path(), default=None, required=False)
@click.option("--stdout", is_flag=True, help="Output to stdout instead of file")
def db_dump(output: str | None, stdout: bool):
    """Dump database to SQL file (FTS5-safe).

    \b
    Examples:
      twag db dump                    # Creates twag-YYYYMMDD-HHMMSS.sql
      twag db dump backup.sql         # Creates backup.sql
      twag db dump --stdout | gzip    # Pipe to compression
    """
    db_file = get_database_path()

    if not db_file.exists():
        click.echo(f"Database not found: {db_file}", err=True)
        sys.exit(1)

    if stdout:
        for stmt in dump_sql(db_file):
            click.echo(stmt)
    else:
        if output is None:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            output = f"twag-{timestamp}.sql"

        output_path = Path(output)

        with open(output_path, "w") as f:
            for stmt in dump_sql(db_file):
                f.write(f"{stmt}\n")

        # Get file size
        size_bytes = output_path.stat().st_size
        if size_bytes >= 1024 * 1024:
            size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
        elif size_bytes >= 1024:
            size_str = f"{size_bytes / 1024:.1f} KB"
        else:
            size_str = f"{size_bytes} bytes"

        click.echo(f"Dumped database to: {output_path} ({size_str})")


@db.command("restore")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--force", is_flag=True, help="Overwrite existing database without prompting")
def db_restore(input_file: str, force: bool):
    """Restore database from SQL dump (handles .gz files).

    \b
    WARNING: This will replace the existing database!
    FTS5 index is rebuilt automatically after restore.

    \b
    Examples:
      twag db restore backup.sql
      twag db restore backup.sql.gz --force
      twag db restore twag-20240115-120000.sql --force
    """
    import gzip

    db_file = get_database_path()
    input_path = Path(input_file)

    # Warn about overwriting
    if db_file.exists() and not force:
        try:
            with get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM tweets")
                tweet_count = cursor.fetchone()[0]
            msg = f"This will replace the existing database ({tweet_count} tweets). Continue?"
        except Exception:
            msg = "This will replace the existing database. Continue?"

        if not click.confirm(msg):
            click.echo("Aborted.")
            return

    click.echo(f"Restoring from: {input_path}")

    # Read the SQL dump, handling .gz transparently
    if input_path.suffix == ".gz" or input_path.name.endswith(".sql.gz"):
        with gzip.open(input_path, "rt", encoding="utf-8") as f:
            sql_script = f.read()
    else:
        with open(input_path) as f:
            sql_script = f.read()

    try:
        counts = restore_sql(sql_script, db_file, backup=True)
        click.echo(
            f"Restored database: {counts['tweets']} tweets, {counts['accounts']} accounts, {counts['fts']} FTS entries"
        )
    except Exception as e:
        click.echo(f"Error restoring database: {e}", err=True)
        sys.exit(1)


# ============================================================================
# Search command
# ============================================================================


@cli.command()
@click.argument("query")
@click.option("--category", "-c", help="Filter by category (fed_policy, equities, etc.)")
@click.option("--author", "-a", help="Filter by author handle")
@click.option("--min-score", "-s", type=float, help="Minimum relevance score")
@click.option("--tier", "-t", help="Filter by signal tier")
@click.option("--ticker", "-T", help="Filter by ticker symbol")
@click.option("--bookmarks", "-b", is_flag=True, help="Only bookmarked tweets")
@click.option("--since", help="Start time (YYYY-MM-DD or relative like 1d, 7d)")
@click.option("--until", help="End time (YYYY-MM-DD)")
@click.option("--today", is_flag=True, help="Since previous market close (4pm ET)")
@click.option("--time", "time_range", help="Time range shorthand (today, 7d, etc.)")
@click.option("--limit", "-n", type=int, default=20, help="Max results (default: 20)")
@click.option(
    "--order",
    "-o",
    type=click.Choice(["rank", "score", "time"]),
    default="rank",
    help="Sort order: rank (relevance), score, time",
)
@click.option(
    "--format", "-f", "fmt", type=click.Choice(["brief", "full", "json"]), default="brief", help="Output format"
)
def search(
    query: str,
    category: str | None,
    author: str | None,
    min_score: float | None,
    tier: str | None,
    ticker: str | None,
    bookmarks: bool,
    since: str | None,
    until: str | None,
    today: bool,
    time_range: str | None,
    limit: int,
    order: str,
    fmt: str,
):
    """
    Search tweets using full-text search.

    \b
    QUERY SYNTAX:
      Simple:    inflation fed
      Phrases:   "rate hike"
      Boolean:   inflation AND fed, fed NOT fomc
      Prefix:    infla*
      Column:    author_handle:zerohedge

    \b
    EXAMPLES:
      twag search "inflation" --today
      twag search "fed rate" -c fed_policy -s 7
      twag search "NVDA" -a zerohedge --time 7d
      twag search "earnings" --ticker AAPL
    """
    # Parse since/until if provided as strings
    since_dt = None
    until_dt = None

    if since:
        since_dt, _ = parse_time_range(since)
    if until:
        _, until_dt = parse_time_range(until)
        if until_dt is None:
            # Try parsing as a single date for "until"
            until_parsed, until_end = parse_time_range(until)
            until_dt = until_end or until_parsed

    # Handle --today flag
    if today:
        time_range = "today"

    # Auto-detect equity context for smart defaults (only if no time specified)
    if not time_range and since_dt is None and query_suggests_equity_context(query):
        click.echo("(auto-detected equity context, defaulting to --today)", err=True)
        time_range = "today"

    with get_connection(readonly=True) as conn:
        results = search_tweets(
            conn,
            query,
            category=category,
            author=author,
            min_score=min_score,
            signal_tier=tier,
            ticker=ticker,
            bookmarked_only=bookmarks,
            since=since_dt,
            until=until_dt,
            time_range=time_range,
            limit=limit,
            order_by=order,
        )

    if not results:
        click.echo("No results found.")
        return

    if fmt == "json":
        _output_json(results)
    elif fmt == "full":
        _output_full(results)
    else:
        _output_brief(results)


def _output_brief(results):
    """Output search results in brief format."""
    for r in results:
        # Format: [8.2] @handle (01/15 14:32) [SPY] Summary...
        score = f"{r.relevance_score:.1f}" if r.relevance_score else "-"
        time_str = r.created_at.strftime("%m/%d %H:%M") if r.created_at else "??/??"
        tickers = f" [{','.join(r.tickers)}]" if r.tickers else ""
        bookmark = "*" if r.bookmarked else ""

        # Use summary if available, else truncate content
        text = r.summary or r.content
        text = text.replace("\n", " ")[:80]

        click.echo(f"[{score}]{bookmark} @{r.author_handle} ({time_str}){tickers} {text}")


def _output_full(results):
    """Output search results in full digest-style format."""
    for i, r in enumerate(results):
        if i > 0:
            click.echo("")
            click.echo("---")
            click.echo("")

        score = f"{r.relevance_score:.1f}" if r.relevance_score else "-"
        time_str = r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "unknown"
        categories = ", ".join(r.categories) if r.categories else "uncategorized"
        bookmark = " [BOOKMARKED]" if r.bookmarked else ""

        click.echo(f"**@{r.author_handle}** [{score}] {categories}{bookmark}")
        click.echo(f"*{time_str}*")

        if r.tickers:
            click.echo(f"Tickers: {', '.join(r.tickers)}")

        click.echo("")

        if r.summary:
            click.echo(f"**Summary:** {r.summary}")
            click.echo("")

        click.echo(r.content)
        click.echo("")
        click.echo(f"https://x.com/{r.author_handle}/status/{r.id}")


def _output_json(results):
    """Output search results as JSON."""
    output = []
    for r in results:
        output.append(
            {
                "id": r.id,
                "author_handle": r.author_handle,
                "author_name": r.author_name,
                "content": r.content,
                "summary": r.summary,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "relevance_score": r.relevance_score,
                "categories": r.categories,
                "signal_tier": r.signal_tier,
                "tickers": r.tickers,
                "bookmarked": r.bookmarked,
                "rank": r.rank,
                "url": f"https://x.com/{r.author_handle}/status/{r.id}",
            }
        )
    click.echo(json.dumps(output, indent=2))


# ============================================================================
# Web server
# ============================================================================


@cli.command()
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=5173, help="Port to bind to")
@click.option("--reload/--no-reload", default=True, help="Auto-reload on code changes")
@click.option("--dev", is_flag=True, default=False, help="Dev mode: start Vite + FastAPI with HMR")
def web(host: str, port: int, reload: bool, dev: bool):
    """Start the web interface server."""
    import os
    import signal
    import subprocess

    project_dir = Path(__file__).parent.parent
    frontend_dir = Path(__file__).parent / "web" / "frontend"

    if dev:
        # Dev mode: start both Vite dev server and FastAPI (API-only)
        if not (frontend_dir / "node_modules").exists():
            click.echo("Installing frontend dependencies...")
            subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)

        click.echo("Starting dev servers:")
        click.echo(f"  Vite (frontend):  http://{host}:8080")
        click.echo(f"  FastAPI (API):    http://{host}:{port}")
        click.echo(f"Open http://{host}:8080 for hot reload")
        click.echo("Press Ctrl+C to stop both")

        env = {**os.environ, "TWAG_DEV": "1"}

        uvicorn_cmd = [
            "uv",
            "run",
            "--project",
            str(project_dir),
            "--with",
            "uvicorn[standard]",
            "uvicorn",
            "twag.web:create_app",
            "--host",
            host,
            "--port",
            str(port),
            "--factory",
        ]
        if reload:
            uvicorn_cmd.append("--reload")

        vite_cmd = ["npm", "run", "dev"]

        procs = []
        try:
            procs.append(subprocess.Popen(uvicorn_cmd, env=env))
            procs.append(subprocess.Popen(vite_cmd, cwd=frontend_dir))

            # Wait for either to exit
            while all(p.poll() is None for p in procs):
                try:
                    procs[0].wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
        except KeyboardInterrupt:
            pass
        finally:
            for p in procs:
                p.send_signal(signal.SIGTERM)
            for p in procs:
                p.wait(timeout=5)
    else:
        click.echo(f"Starting twag web interface at http://{host}:{port}")
        click.echo("Press Ctrl+C to stop")

        cmd = [
            "uv",
            "run",
            "--project",
            str(project_dir),
            "--with",
            "uvicorn[standard]",
            "uvicorn",
            "twag.web:create_app",
            "--host",
            host,
            "--port",
            str(port),
            "--factory",
        ]
        if reload:
            cmd.append("--reload")

        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            click.echo("Error: 'uv' not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh", err=True)
            sys.exit(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    cli()
