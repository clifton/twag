"""Analyze command."""

import shutil
import textwrap

import rich_click as click

from ..article_sections import parse_action_items, parse_primary_points
from ..article_visuals import build_article_visuals
from ..db import get_connection, get_tweet_by_id, init_db
from ._console import console
from ._helpers import _json_list, _json_object, _normalize_status_id_or_url
from ._progress import RichProgressReporter, create_progress, make_callbacks


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
    click.echo(f"@{row['author_handle']} \u00b7 {row['id']}")
    click.echo(f"Score: {score:.1f} \u00b7 Tier: {row['signal_tier'] or '-'}")
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


@click.command()
@click.argument("status_id_or_url")
@click.option("--model", "-m", help="Override triage model")
@click.option("--reprocess/--no-reprocess", default=False, help="Reprocess even if already processed")
def analyze(status_id_or_url: str, model: str | None, reprocess: bool):
    """Fetch, process, and print structured analysis for one status."""
    from ..fetcher import read_tweet
    from ..processor import process_unprocessed, store_fetched_tweets

    init_db()
    normalized_id = _normalize_status_id_or_url(status_id_or_url)
    console.print(f"Analyzing status {normalized_id}...")

    tweet = read_tweet(status_id_or_url)
    if not tweet:
        raise click.ClickException(f"Status not found or unreadable: {status_id_or_url}")

    with create_progress() as progress:
        task_id = progress.add_task("Storing status (0/1)", total=1)
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

    with get_connection() as conn:
        row = get_tweet_by_id(conn, tweet.id) or get_tweet_by_id(conn, normalized_id)

    if not row:
        raise click.ClickException(f"Status not found in database after fetch: {normalized_id}")

    if row["processed_at"] and not reprocess:
        console.print("Status already processed; using existing analysis (pass --reprocess to refresh).")
    else:
        with create_progress() as progress:
            task_id = progress.add_task("Processing status (0/1)", total=1)
            reporter = RichProgressReporter(progress, task_id, "Processing status")
            reporter.set_total(1)
            status_cb, progress_cb, total_cb = make_callbacks(reporter)
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
