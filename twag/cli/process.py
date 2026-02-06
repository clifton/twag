"""Process command."""

from datetime import datetime

import rich_click as click

from ..config import load_config
from ..db import get_connection, get_tweet_by_id, get_unprocessed_tweets, init_db
from ._console import console
from ._helpers import _normalize_status_id_or_url
from ._progress import RichProgressReporter, create_progress, make_callbacks


@click.command()
@click.argument("status_id_or_url", required=False)
@click.option("--limit", "-n", default=250, help="Max tweets to process")
@click.option("--dry-run", is_flag=True, help="Show what would be processed")
@click.option("--model", "-m", help="Override triage model")
@click.option("--notify/--no-notify", default=True, help="Send Telegram alerts")
@click.option(
    "--reprocess-quotes/--no-reprocess-quotes",
    default=True,
    help="Reprocess today's dependency tweets (quotes/replies)",
)
@click.option("--reprocess-min-score", type=float, default=None, help="Min score for reprocessing dependency tweets")
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
    from ..notifier import notify_high_signal_tweet
    from ..processor import process_unprocessed, reprocess_today_quoted

    init_db()

    target_tweet_id = _normalize_status_id_or_url(status_id_or_url) if status_id_or_url else None
    if target_tweet_id:
        console.print(f"Processing status {target_tweet_id}...")
    else:
        console.print(f"Processing up to {limit} tweets...")

    if dry_run:
        console.print("(dry run - no changes will be made)")

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
        with create_progress() as progress:
            task_id = progress.add_task("Processing tweets", total=len(unprocessed_rows))
            reporter = RichProgressReporter(progress, task_id, "Processing tweets")
            reporter.set_total(len(unprocessed_rows))
            status_cb, progress_cb, total_cb = make_callbacks(reporter)

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
        console.print("No unprocessed tweets found.")
    else:
        # Show results
        high_signal = [r for r in results if r.score >= 8]
        market_relevant = [r for r in results if 6 <= r.score < 8]

        console.print(f"Processed {len(results)} tweets:")
        console.print(f"  High signal: {len(high_signal)}")
        console.print(f"  Market relevant: {len(market_relevant)}")

        # Show high signal tweets
        if high_signal:
            console.print("\nHigh Signal:")
            for r in high_signal[:5]:
                console.print(f"  [{r.score:.1f}] {', '.join(r.categories)}: {r.summary[:60]}")

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
        console.print("Skipping dependency reprocessing for single-status mode.")
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
                  AND (
                    (has_quote = 1 AND quote_tweet_id IS NOT NULL)
                    OR in_reply_to_tweet_id IS NOT NULL
                  )
                  AND quote_reprocessed_at IS NULL
                  AND date(created_at) = ?
                  AND relevance_score >= ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (today, min_score, reprocess_limit),
            )
            quote_rows = cursor.fetchall()

        console.print("Reprocessing today's dependency tweets...")
        if quote_rows:
            with create_progress() as progress:
                task_id = progress.add_task("Reprocessing dependencies", total=len(quote_rows))
                reporter = RichProgressReporter(progress, task_id, "Reprocessing dependencies")
                reporter.set_total(len(quote_rows))
                status_cb, progress_cb, _ = make_callbacks(reporter)

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
            console.print(f"Reprocessed {len(reprocessed)} dependency tweets.")
        else:
            console.print("No dependency tweets to reprocess.")
