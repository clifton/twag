"""Top-level orchestration: process, reprocess, enrich, full cycle."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from ..config import load_config
from ..db import (
    get_accounts,
    get_connection,
    get_tweet_by_id,
    get_unprocessed_tweets,
)
from ..fetcher import read_tweet
from ..media import build_media_context
from ..scorer import EnrichmentResult, TriageResult, enrich_tweet
from .dependencies import _expand_links_for_rows, _expand_unprocessed_with_dependencies
from .storage import fetch_and_store
from .triage import (
    _normalized_worker_count,
    _triage_rows,
    ensure_media_analysis,
)

log = logging.getLogger(__name__)


def process_unprocessed(
    limit: int = 50,
    dry_run: bool = False,
    triage_model: str | None = None,
    enrich_model: str | None = None,
    rows: list[sqlite3.Row] | None = None,
    progress_cb: Callable[[int], None] | None = None,
    status_cb: Callable[[str], None] | None = None,
    total_cb: Callable[[int], None] | None = None,
    force_refresh: bool = False,
) -> list[TriageResult]:
    """Process tweets that haven't been scored yet."""
    config = load_config()
    batch_size = config["scoring"]["batch_size"]
    high_threshold = config["scoring"]["high_signal_threshold"]
    media_min_score = config["scoring"].get("min_score_for_media", 3)
    quote_depth = config.get("fetch", {}).get("quote_depth", 0)
    quote_delay = config.get("fetch", {}).get("quote_delay", 1.0)
    url_expansion_workers = _normalized_worker_count(
        config.get("processing", {}).get("max_concurrency_url_expansion", 15),
        15,
    )

    with get_connection() as conn:
        unprocessed = rows if rows is not None else get_unprocessed_tweets(conn, limit=limit)

        if not unprocessed:
            return []

        if quote_depth > 0:
            if status_cb:
                status_cb("Expanding dependency tweets")
            unprocessed = _expand_unprocessed_with_dependencies(
                conn,
                unprocessed,
                max_depth=quote_depth,
                delay=quote_delay,
                fetch_missing=not dry_run,
                status_cb=status_cb,
                total_cb=total_cb,
            )

        if not dry_run:
            unprocessed = _expand_links_for_rows(
                conn,
                unprocessed,
                max_workers=url_expansion_workers,
                quote_depth=max(1, quote_depth),
                status_cb=status_cb,
            )

        if total_cb:
            total_cb(len(unprocessed))

        # Get tier-1 handles for summarization check
        tier1_accounts = get_accounts(conn, tier=1)
        tier1_handles = {a["handle"].lower() for a in tier1_accounts}

        # Prepare tweets for batch triage
        tweets_for_triage = []
        tweet_map: dict[str, sqlite3.Row] = {}

        for row in unprocessed:
            tweet_id = row["id"]
            tweets_for_triage.append(
                {
                    "id": tweet_id,
                    "text": row["content"],
                    "handle": row["author_handle"],
                }
            )
            tweet_map[tweet_id] = row

        if dry_run:
            if progress_cb:
                for row in unprocessed:
                    if status_cb:
                        status_cb(f"Dry run @{row['author_handle']}")
                    progress_cb(1)
            return [
                TriageResult(
                    tweet_id=t["id"],
                    score=0,
                    categories=["dry_run"],
                    summary=f"[DRY RUN] @{t['handle']}: {t['text'][:50]}...",
                )
                for t in tweets_for_triage
            ]

        results = _triage_rows(
            conn,
            tweet_rows=unprocessed,
            batch_size=batch_size,
            triage_model=triage_model,
            enrich_model=enrich_model,
            high_threshold=high_threshold,
            tier1_handles=tier1_handles,
            update_stats=True,
            allow_summarize=True,
            media_min_score=media_min_score,
            progress_cb=progress_cb,
            status_cb=status_cb,
            force_refresh=force_refresh,
        )

        conn.commit()

    return results


def reprocess_today_quoted(
    limit: int = 200,
    min_score: float | None = None,
    dry_run: bool = False,
    triage_model: str | None = None,
    rows: list[sqlite3.Row] | None = None,
    progress_cb: Callable[[int], None] | None = None,
    status_cb: Callable[[str], None] | None = None,
) -> list[TriageResult]:
    """Reprocess today's already-processed tweets with dependency context."""
    config = load_config()
    batch_size = config["scoring"]["batch_size"]
    high_threshold = config["scoring"]["high_signal_threshold"]
    min_score = min_score if min_score is not None else config["scoring"].get("min_score_for_reprocess", 3)
    quote_depth = config.get("fetch", {}).get("quote_depth", 0)
    url_expansion_workers = _normalized_worker_count(
        config.get("processing", {}).get("max_concurrency_url_expansion", 15),
        15,
    )

    today = datetime.now().strftime("%Y-%m-%d")

    with get_connection() as conn:
        if rows is None:
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
                (today, min_score, limit),
            )
            rows = cursor.fetchall()

        if not rows:
            return []

        if dry_run:
            if progress_cb:
                for row in rows:
                    if status_cb:
                        status_cb(f"Dry run @{row['author_handle']}")
                    progress_cb(1)
            return [
                TriageResult(
                    tweet_id=row["id"],
                    score=0,
                    categories=["dry_run"],
                    summary=f"[DRY RUN] @{row['author_handle']}: {row['content'][:50]}...",
                )
                for row in rows
            ]

        rows = _expand_links_for_rows(
            conn,
            rows,
            max_workers=url_expansion_workers,
            quote_depth=max(1, quote_depth),
            status_cb=status_cb,
        )

        tier1_accounts = get_accounts(conn, tier=1)
        tier1_handles = {a["handle"].lower() for a in tier1_accounts}

        results = _triage_rows(
            conn,
            tweet_rows=rows,
            batch_size=batch_size,
            triage_model=triage_model,
            enrich_model=None,
            high_threshold=high_threshold,
            tier1_handles=tier1_handles,
            update_stats=False,
            allow_summarize=False,
            media_min_score=config["scoring"].get("min_score_for_media", 3),
            progress_cb=progress_cb,
            status_cb=status_cb,
        )

        # Mark all reprocessed tweets so they aren't reprocessed again
        now = datetime.now().isoformat()
        tweet_ids = [row["id"] for row in rows]
        conn.executemany(
            "UPDATE tweets SET quote_reprocessed_at = ? WHERE id = ?",
            [(now, tid) for tid in tweet_ids],
        )

        conn.commit()

    return results


def enrich_high_signal(
    limit: int = 10,
    enrich_model: str | None = None,
) -> list[EnrichmentResult]:
    """Enrich high-signal tweets with deeper analysis."""
    config = load_config()
    high_threshold = config["scoring"]["high_signal_threshold"]
    max_text_workers = _normalized_worker_count(config.get("llm", {}).get("max_concurrency_text", 8), 8)

    with get_connection() as conn:
        # Get high-signal tweets that need enrichment
        cursor = conn.execute(
            """
            SELECT * FROM tweets
            WHERE relevance_score >= ?
            AND signal_tier IS NOT NULL
            AND (
                (has_quote = 1 AND quote_tweet_id IS NOT NULL AND media_analysis IS NULL)
                OR (has_link = 1 AND link_summary IS NULL)
                OR (has_media = 1 AND media_analysis IS NULL)
            )
            ORDER BY relevance_score DESC
            LIMIT ?
            """,
            (high_threshold, limit),
        )
        tweets = cursor.fetchall()

        if not tweets:
            return []

        author_handles = {tweet["author_handle"] for tweet in tweets}
        account_categories: dict[str, str | None] = {}
        if author_handles:
            placeholders = ",".join("?" for _ in author_handles)
            acct_cursor = conn.execute(
                f"SELECT handle, category FROM accounts WHERE handle IN ({placeholders})",
                tuple(author_handles),
            )
            account_categories = {row["handle"]: row["category"] for row in acct_cursor.fetchall()}

        results: list[EnrichmentResult] = []
        futures = {}
        text_pool = (
            ThreadPoolExecutor(max_workers=max_text_workers) if max_text_workers and max_text_workers > 1 else None
        )

        try:
            for tweet in tweets:
                quoted_text = ""
                if tweet["has_quote"] and tweet["quote_tweet_id"]:
                    quoted_row = get_tweet_by_id(conn, tweet["quote_tweet_id"])
                    if quoted_row:
                        quoted_text = f"@{quoted_row['author_handle']}: {quoted_row['content']}"
                    else:
                        quoted = read_tweet(tweet["quote_tweet_id"])
                        if quoted:
                            quoted_text = f"@{quoted.author_handle}: {quoted.content}"
                        else:
                            log.warning("Could not fetch quoted tweet %s for enrichment", tweet["quote_tweet_id"])

                media_items = ensure_media_analysis(conn, tweet)
                media_context = build_media_context(media_items) if media_items else (tweet["media_analysis"] or "")

                author_category = account_categories.get(tweet["author_handle"]) or "unknown"

                if text_pool:
                    future = text_pool.submit(
                        enrich_tweet,
                        tweet_text=tweet["content"],
                        handle=tweet["author_handle"],
                        author_category=author_category or "unknown",
                        quoted_tweet=quoted_text,
                        article_summary=tweet["article_summary_short"] or tweet["link_summary"] or "",
                        image_description=media_context,
                        model=enrich_model,
                    )
                    futures[future] = (tweet["id"], tweet["signal_tier"])
                else:
                    result = enrich_tweet(
                        tweet_text=tweet["content"],
                        handle=tweet["author_handle"],
                        author_category=author_category or "unknown",
                        quoted_tweet=quoted_text,
                        article_summary=tweet["article_summary_short"] or tweet["link_summary"] or "",
                        image_description=media_context,
                        model=enrich_model,
                    )
                    results.append(result)

                    if result.signal_tier != tweet["signal_tier"]:
                        conn.execute(
                            "UPDATE tweets SET signal_tier = ? WHERE id = ?",
                            (result.signal_tier, tweet["id"]),
                        )

            for future in as_completed(list(futures.keys())):
                tweet_id, current_tier = futures.pop(future)
                try:
                    result = future.result()
                    results.append(result)
                    if result.signal_tier != current_tier:
                        conn.execute(
                            "UPDATE tweets SET signal_tier = ? WHERE id = ?",
                            (result.signal_tier, tweet_id),
                        )
                except Exception:
                    continue
        finally:
            if text_pool:
                text_pool.shutdown(wait=True)

        conn.commit()

    return results


def run_full_cycle(
    fetch_home: bool = True,
    fetch_tier1: bool = True,
    process: bool = True,
    enrich: bool = True,
) -> dict:
    """Run a full fetch/process/enrich cycle."""
    stats = {
        "home_fetched": 0,
        "home_new": 0,
        "tier1_fetched": 0,
        "tier1_new": 0,
        "processed": 0,
        "enriched": 0,
    }

    # Fetch home timeline
    if fetch_home:
        fetched, new = fetch_and_store(source="home", count=100)
        stats["home_fetched"] = fetched
        stats["home_new"] = new

    # Fetch tier-1 accounts
    if fetch_tier1:
        with get_connection() as conn:
            tier1 = get_accounts(conn, tier=1)

        for account in tier1:
            try:
                fetched, new = fetch_and_store(
                    source="user",
                    handle=account["handle"],
                    count=20,
                )
                stats["tier1_fetched"] += fetched
                stats["tier1_new"] += new
            except Exception:
                # Log but continue
                pass

    # Process unprocessed tweets
    if process:
        results = process_unprocessed(limit=100)
        stats["processed"] = len(results)

    # Enrich high-signal tweets
    if enrich:
        results = enrich_high_signal(limit=20)
        stats["enriched"] = len(results)

    return stats
