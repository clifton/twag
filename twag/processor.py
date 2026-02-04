"""Tweet processing pipeline."""

import time
import sqlite3
import re
import json
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable
from datetime import datetime, timezone

from .config import load_config
from .db import (
    get_accounts,
    get_authors_to_promote,
    get_connection,
    get_unprocessed_tweets,
    get_tweet_by_id,
    insert_tweet,
    is_tweet_seen,
    log_fetch,
    mark_tweet_bookmarked,
    promote_account,
    update_account_stats,
    update_tweet_analysis,
    update_tweet_enrichment,
    update_tweet_processing,
    upsert_account,
)
from .fetcher import (
    Tweet,
    fetch_bookmarks,
    fetch_home_timeline,
    fetch_search,
    fetch_user_tweets,
    read_tweet,
)
from .media import build_media_context, build_media_summary, parse_media_items
from .scorer import (
    EnrichmentResult,
    TriageResult,
    analyze_media,
    enrich_tweet,
    summarize_document_text,
    summarize_tweet,
    triage_tweets_batch,
)


def _fetch_quote_chain(
    conn: sqlite3.Connection,
    tweet: Tweet,
    *,
    source: str,
    max_depth: int,
    delay: float,
    seen: set[str],
    status_cb: Callable[[str], None] | None = None,
) -> int:
    if max_depth <= 0:
        return 0
    if not tweet.has_quote or not tweet.quote_tweet_id:
        return 0
    return _fetch_quote_by_id(
        conn,
        tweet.quote_tweet_id,
        source=source,
        remaining_depth=max_depth,
        delay=delay,
        seen=seen,
        status_cb=status_cb,
    )


def _fetch_quote_by_id(
    conn: sqlite3.Connection,
    quote_id: str,
    *,
    source: str,
    remaining_depth: int,
    delay: float,
    seen: set[str],
    status_cb: Callable[[str], None] | None = None,
) -> int:
    if remaining_depth <= 0 or not quote_id:
        return 0
    if quote_id in seen:
        return 0
    seen.add(quote_id)

    if is_tweet_seen(conn, quote_id):
        row = get_tweet_by_id(conn, quote_id)
        if row and row["has_quote"] and row["quote_tweet_id"]:
            return _fetch_quote_by_id(
                conn,
                row["quote_tweet_id"],
                source=source,
                remaining_depth=remaining_depth - 1,
                delay=delay,
                seen=seen,
                status_cb=status_cb,
            )
        return 0

    if delay and delay > 0:
        conn.commit()
        time.sleep(delay)

    if status_cb:
        status_cb(f"Fetching quoted tweet {quote_id}")

    quoted = read_tweet(quote_id)
    if not quoted or not quoted.id:
        return 0

    inserted = insert_tweet(
        conn,
        tweet_id=quoted.id,
        author_handle=quoted.author_handle,
        author_name=quoted.author_name,
        content=quoted.content,
        created_at=quoted.created_at,
        source=source,
        has_quote=quoted.has_quote,
        quote_tweet_id=quoted.quote_tweet_id,
        has_media=quoted.has_media,
        media_items=quoted.media_items,
        has_link=quoted.has_link,
    )
    if inserted:
        upsert_account(conn, quoted.author_handle, quoted.author_name)

    total = 1 if inserted else 0
    if quoted.has_quote and quoted.quote_tweet_id:
        total += _fetch_quote_by_id(
            conn,
            quoted.quote_tweet_id,
            source=source,
            remaining_depth=remaining_depth - 1,
            delay=delay,
            seen=seen,
            status_cb=status_cb,
        )
    return total


def _ensure_quote_row(
    conn: sqlite3.Connection,
    quote_id: str,
    *,
    delay: float,
    status_cb: Callable[[str], None] | None = None,
) -> sqlite3.Row | None:
    row = get_tweet_by_id(conn, quote_id)
    if row:
        return row

    if delay and delay > 0:
        conn.commit()
        time.sleep(delay)

    if status_cb:
        status_cb(f"Fetching quoted tweet {quote_id}")

    quoted = read_tweet(quote_id)
    if not quoted or not quoted.id:
        return None

    inserted = insert_tweet(
        conn,
        tweet_id=quoted.id,
        author_handle=quoted.author_handle,
        author_name=quoted.author_name,
        content=quoted.content,
        created_at=quoted.created_at,
        source="quote",
        has_quote=quoted.has_quote,
        quote_tweet_id=quoted.quote_tweet_id,
        has_media=quoted.has_media,
        media_items=quoted.media_items,
        has_link=quoted.has_link,
    )
    if inserted:
        upsert_account(conn, quoted.author_handle, quoted.author_name)

    return get_tweet_by_id(conn, quoted.id)


def _expand_unprocessed_with_quotes(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    *,
    max_depth: int,
    delay: float,
    fetch_missing: bool = True,
    status_cb: Callable[[str], None] | None = None,
    total_cb: Callable[[int], None] | None = None,
) -> list[sqlite3.Row]:
    if max_depth <= 0:
        return rows

    expanded: list[sqlite3.Row] = list(rows)
    process_ids: set[str] = {row["id"] for row in rows}
    seen_quote_ids: set[str] = set()

    queue: deque[tuple[sqlite3.Row, int]] = deque((row, 0) for row in rows)

    while queue:
        row, depth = queue.popleft()
        if depth >= max_depth:
            continue
        if not row["has_quote"] or not row["quote_tweet_id"]:
            continue

        quote_id = row["quote_tweet_id"]
        if not quote_id or quote_id in seen_quote_ids:
            continue
        seen_quote_ids.add(quote_id)

        quote_row = get_tweet_by_id(conn, quote_id)
        if not quote_row and fetch_missing:
            quote_row = _ensure_quote_row(conn, quote_id, delay=delay, status_cb=status_cb)
        if not quote_row:
            continue

        queue.append((quote_row, depth + 1))

        if quote_row["processed_at"] is None and quote_id not in process_ids:
            process_ids.add(quote_id)
            expanded.append(quote_row)
            if total_cb:
                total_cb(len(expanded))

    return expanded


def store_fetched_tweets(
    tweets: list[Tweet],
    *,
    source: str,
    query_params: dict[str, Any] | None = None,
    quote_depth: int | None = None,
    quote_delay: float | None = None,
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[int], None] | None = None,
) -> tuple[int, int]:
    """Store fetched tweets with optional progress callbacks."""
    config = load_config()
    quote_depth = quote_depth if quote_depth is not None else config.get("fetch", {}).get("quote_depth", 0)
    quote_delay = quote_delay if quote_delay is not None else config.get("fetch", {}).get("quote_delay", 1.0)

    fetched = len(tweets)
    new_count = 0
    seen_quotes: set[str] = set()

    with get_connection() as conn:
        for idx, tweet in enumerate(tweets, start=1):
            if not tweet.id:
                if progress_cb:
                    progress_cb(1)
                continue

            if status_cb:
                status_cb(f"Storing @{tweet.author_handle}")

            inserted = insert_tweet(
                conn,
                tweet_id=tweet.id,
                author_handle=tweet.author_handle,
                author_name=tweet.author_name,
                content=tweet.content,
                created_at=tweet.created_at,
                source=source,
                has_quote=tweet.has_quote,
                quote_tweet_id=tweet.quote_tweet_id,
                has_media=tweet.has_media,
                media_items=tweet.media_items,
                has_link=tweet.has_link,
            )

            if inserted:
                new_count += 1
                upsert_account(conn, tweet.author_handle, tweet.author_name)
                if quote_depth > 0:
                    _fetch_quote_chain(
                        conn,
                        tweet,
                        source="quote",
                        max_depth=quote_depth,
                        delay=quote_delay,
                        seen=seen_quotes,
                        status_cb=status_cb,
                    )

            if progress_cb:
                progress_cb(1)

        log_fetch(
            conn,
            endpoint=source,
            tweets_fetched=fetched,
            new_tweets=new_count,
            query_params=query_params or {},
        )
        conn.commit()

    return fetched, new_count


def store_bookmarked_tweets(
    tweets: list[Tweet],
    *,
    quote_depth: int | None = None,
    quote_delay: float | None = None,
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[int], None] | None = None,
) -> tuple[int, int]:
    """Store bookmarked tweets with optional progress callbacks."""
    config = load_config()
    quote_depth = quote_depth if quote_depth is not None else config.get("fetch", {}).get("quote_depth", 0)
    quote_delay = quote_delay if quote_delay is not None else config.get("fetch", {}).get("quote_delay", 1.0)

    fetched = len(tweets)
    new_count = 0
    seen_quotes: set[str] = set()

    with get_connection() as conn:
        for idx, tweet in enumerate(tweets, start=1):
            if not tweet.id:
                if progress_cb:
                    progress_cb(1)
                continue

            if status_cb:
                status_cb(f"Storing bookmark @{tweet.author_handle}")

            inserted = insert_tweet(
                conn,
                tweet_id=tweet.id,
                author_handle=tweet.author_handle,
                author_name=tweet.author_name,
                content=tweet.content,
                created_at=tweet.created_at,
                source="bookmarks",
                has_quote=tweet.has_quote,
                quote_tweet_id=tweet.quote_tweet_id,
                has_media=tweet.has_media,
                media_items=tweet.media_items,
                has_link=tweet.has_link,
            )

            if inserted:
                new_count += 1

            mark_tweet_bookmarked(conn, tweet.id)
            upsert_account(conn, tweet.author_handle, tweet.author_name)

            if inserted and quote_depth > 0:
                _fetch_quote_chain(
                    conn,
                    tweet,
                    source="quote",
                    max_depth=quote_depth,
                    delay=quote_delay,
                    seen=seen_quotes,
                    status_cb=status_cb,
                )

            if progress_cb:
                progress_cb(1)

        log_fetch(
            conn,
            endpoint="bookmarks",
            tweets_fetched=fetched,
            new_tweets=new_count,
        )

        conn.commit()

    return fetched, new_count


def ensure_media_analysis(
    conn: sqlite3.Connection,
    tweet_row: sqlite3.Row,
    *,
    vision_model: str | None = None,
    vision_provider: str | None = None,
) -> list[dict[str, Any]]:
    if not tweet_row["has_media"]:
        return []

    media_items = parse_media_items(tweet_row["media_items"])
    if not media_items:
        return []

    media_items, updated = _analyze_media_items(
        media_items,
        vision_model=vision_model,
        vision_provider=vision_provider,
    )

    if updated or (media_items and not tweet_row["media_analysis"]):
        media_summary = build_media_summary(media_items)
        update_tweet_enrichment(
            conn,
            tweet_id=tweet_row["id"],
            media_analysis=media_summary,
            media_items=media_items,
        )

    return media_items


def _analyze_media_items(
    media_items: list[dict[str, Any]],
    *,
    vision_model: str | None = None,
    vision_provider: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    updated = False
    for item in media_items:
        if item.get("kind") or item.get("prose_text") or item.get("short_description"):
            continue
        url = item.get("url")
        if not url:
            continue
        try:
            result = analyze_media(url, model=vision_model, provider=vision_provider)
        except Exception:
            continue

        item["kind"] = result.kind
        item["short_description"] = result.short_description
        item["prose_text"] = result.prose_text
        item["prose_summary"] = result.prose_summary
        item["chart"] = result.chart
        updated = True

    if _merge_document_media(media_items):
        updated = True

    return media_items, updated


def _page_number_hint(text: str) -> int | None:
    match = re.search(r"\bpage\s*(\d+)\b", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"\b(\d+)\s*/\s*(\d+)\b", text)
    if match:
        return int(match.group(1))
    return None


def _merge_document_media(media_items: list[dict[str, Any]]) -> bool:
    doc_entries: list[tuple[int | None, int, str]] = []
    for idx, item in enumerate(media_items):
        kind = (item.get("kind") or "").lower()
        if kind not in {"document", "screenshot"}:
            continue
        text = (item.get("prose_text") or "").strip()
        if not text:
            continue
        doc_entries.append((_page_number_hint(text), idx, text))

    if len(doc_entries) < 2:
        return False

    if any(entry[0] is not None for entry in doc_entries):
        doc_entries.sort(key=lambda entry: (entry[0] is None, entry[0] or 0, entry[1]))
    else:
        doc_entries.sort(key=lambda entry: entry[1])

    combined_text = "\n\n".join(entry[2] for entry in doc_entries).strip()
    if not combined_text:
        return False

    try:
        combined_summary = summarize_document_text(combined_text)
    except Exception:
        combined_summary = (media_items[doc_entries[0][1]].get("prose_summary") or "").strip()

    primary_idx = doc_entries[0][1]
    media_items[primary_idx]["prose_text"] = combined_text
    media_items[primary_idx]["prose_summary"] = combined_summary

    for _, idx, _ in doc_entries[1:]:
        media_items[idx]["prose_text"] = ""
        media_items[idx]["prose_summary"] = ""
        media_items[idx]["short_description"] = ""

    return True


def _needs_media_analysis(media_items: list[dict[str, Any]]) -> bool:
    for item in media_items:
        if not item.get("url"):
            continue
        if item.get("kind") or item.get("prose_text") or item.get("short_description"):
            continue
        return True
    return False


def fetch_and_store(
    source: str = "home",
    handle: str | None = None,
    query: str | None = None,
    count: int = 100,
) -> tuple[int, int]:
    """Fetch tweets and store new ones. Returns (fetched, new) counts."""
    # Fetch based on source
    if source == "home":
        tweets = fetch_home_timeline(count=count)
    elif source == "user" and handle:
        tweets = fetch_user_tweets(handle=handle, count=count)
    elif source == "search" and query:
        tweets = fetch_search(query=query, count=count)
    else:
        raise ValueError(f"Invalid source/parameters: {source}")

    return store_fetched_tweets(
        tweets,
        source=source,
        query_params={"handle": handle, "query": query, "count": count},
    )


def process_unprocessed(
    limit: int = 50,
    dry_run: bool = False,
    triage_model: str | None = None,
    enrich_model: str | None = None,
    rows: list[sqlite3.Row] | None = None,
    progress_cb: Callable[[int], None] | None = None,
    status_cb: Callable[[str], None] | None = None,
    total_cb: Callable[[int], None] | None = None,
) -> list[TriageResult]:
    """Process tweets that haven't been scored yet."""
    config = load_config()
    batch_size = config["scoring"]["batch_size"]
    high_threshold = config["scoring"]["high_signal_threshold"]
    media_min_score = config["scoring"].get("min_score_for_media", 3)
    quote_depth = config.get("fetch", {}).get("quote_depth", 0)
    quote_delay = config.get("fetch", {}).get("quote_delay", 1.0)

    with get_connection() as conn:
        unprocessed = rows if rows is not None else get_unprocessed_tweets(conn, limit=limit)

        if not unprocessed:
            return []

        if quote_depth > 0:
            if status_cb:
                status_cb("Expanding quoted tweets")
            unprocessed = _expand_unprocessed_with_quotes(
                conn,
                unprocessed,
                max_depth=quote_depth,
                delay=quote_delay,
                fetch_missing=not dry_run,
                status_cb=status_cb,
                total_cb=total_cb,
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
            tweets_for_triage.append({
                "id": tweet_id,
                "text": row["content"],
                "handle": row["author_handle"],
            })
            tweet_map[tweet_id] = row

        if dry_run:
            if progress_cb:
                total = len(tweets_for_triage)
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
        )

        conn.commit()

    return results


def _triage_rows(
    conn: sqlite3.Connection,
    *,
    tweet_rows: list[sqlite3.Row],
    batch_size: int,
    triage_model: str | None,
    enrich_model: str | None,
    high_threshold: float,
    tier1_handles: set[str],
    update_stats: bool,
    allow_summarize: bool,
    media_min_score: float | None = None,
    progress_cb: Callable[[int], None] | None = None,
    status_cb: Callable[[str], None] | None = None,
) -> list[TriageResult]:
    """Run triage on provided rows and persist results."""
    config = load_config()
    max_text_workers = config.get("llm", {}).get("max_concurrency_text", 5)
    max_vision_workers = config.get("llm", {}).get("max_concurrency_vision", 3)
    vision_model = config["llm"].get("vision_model")
    vision_provider = config["llm"].get("vision_provider")
    analysis_min_score = config.get("scoring", {}).get("min_score_for_analysis", 3)
    tweets_for_triage = []
    tweet_map: dict[str, sqlite3.Row] = {}

    for row in tweet_rows:
        tweet_id = row["id"]
        tweets_for_triage.append({
            "id": tweet_id,
            "text": row["content"],
            "handle": row["author_handle"],
        })
        tweet_map[tweet_id] = row

    all_results: list[TriageResult] = []

    total = len(tweets_for_triage)
    total_batches = (total + batch_size - 1) // batch_size

    pending_tasks: dict[str, int] = {}
    summary_futures = {}
    media_futures = {}
    enrich_futures = {}
    enrich_candidates: set[str] = set()

    text_pool = ThreadPoolExecutor(max_workers=max_text_workers) if max_text_workers and max_text_workers > 1 else None
    vision_pool = ThreadPoolExecutor(max_workers=max_vision_workers) if max_vision_workers and max_vision_workers > 1 else None

    def _complete_task(tweet_id: str) -> None:
        if tweet_id not in pending_tasks:
            return
        pending_tasks[tweet_id] -= 1
        if pending_tasks[tweet_id] <= 0:
            pending_tasks.pop(tweet_id, None)
            if progress_cb:
                progress_cb(1)

    def _handle_results(results: list[TriageResult]) -> None:
        for result in results:
            tweet_row = tweet_map.get(result.tweet_id)
            if status_cb and tweet_row:
                status_cb(f"Saving @{tweet_row['author_handle']}")

            if result.score >= 8:
                tier = "high_signal"
            elif result.score >= 6:
                tier = "market_relevant"
            elif result.score >= 4:
                tier = "news"
            else:
                tier = "noise"

            update_tweet_processing(
                conn,
                tweet_id=result.tweet_id,
                relevance_score=result.score,
                categories=result.categories,
                summary=result.summary,
                signal_tier=tier,
                tickers=result.tickers,
            )

            if not tweet_row:
                if progress_cb:
                    progress_cb(1)
                continue

            content = tweet_row["content"]
            handle = tweet_row["author_handle"]
            is_tier1 = handle.lower() in tier1_handles

            task_count = 0

            if allow_summarize and len(content) > 500 and not is_tier1 and result.score >= 5:
                if text_pool:
                    if status_cb:
                        status_cb(f"Queue summary @{handle}")
                    future = text_pool.submit(summarize_tweet, content, handle, enrich_model, None)
                    summary_futures[future] = result.tweet_id
                    task_count += 1
                else:
                    try:
                        if status_cb:
                            status_cb(f"Summarizing @{handle}")
                        content_summary = summarize_tweet(
                            tweet_text=content,
                            handle=handle,
                            model=enrich_model,
                        )
                        update_tweet_enrichment(
                            conn,
                            tweet_id=result.tweet_id,
                            content_summary=content_summary,
                        )
                    except Exception:
                        pass

            if update_stats:
                update_account_stats(
                    conn,
                    handle=handle,
                    score=result.score,
                    is_high_signal=result.score >= high_threshold,
                )

            if media_min_score is not None and result.score >= media_min_score:
                media_items = parse_media_items(tweet_row["media_items"])
                if media_items:
                    if not _needs_media_analysis(media_items):
                        media_summary = build_media_summary(media_items)
                        if media_summary and tweet_row["media_analysis"] != media_summary:
                            update_tweet_enrichment(
                                conn,
                                tweet_id=result.tweet_id,
                                media_analysis=media_summary,
                                media_items=media_items,
                            )
                    elif vision_pool:
                        if status_cb:
                            status_cb(f"Queue media @{handle}")
                        future = vision_pool.submit(
                            _analyze_media_items,
                            media_items,
                            vision_model=vision_model,
                            vision_provider=vision_provider,
                        )
                        media_futures[future] = result.tweet_id
                        task_count += 1
                    else:
                        if status_cb:
                            status_cb(f"Analyzing media @{handle}")
                        updated_items, _ = _analyze_media_items(
                            media_items,
                            vision_model=vision_model,
                            vision_provider=vision_provider,
                        )
                        media_summary = build_media_summary(updated_items)
                        update_tweet_enrichment(
                            conn,
                            tweet_id=result.tweet_id,
                            media_analysis=media_summary,
                            media_items=updated_items,
                        )

            needs_analysis = (
                analysis_min_score is not None
                and result.score >= analysis_min_score
                and tweet_row is not None
                and not tweet_row["analysis_json"]
            )
            if needs_analysis:
                enrich_candidates.add(result.tweet_id)
                task_count += 1

            if task_count:
                pending_tasks[result.tweet_id] = task_count
            else:
                if progress_cb:
                    progress_cb(1)

    try:
        if text_pool:
            batch_futures: dict[Any, tuple[int, int]] = {}
            for i in range(0, total, batch_size):
                batch_index = (i // batch_size) + 1
                if status_cb:
                    status_cb(f"Queue batch {batch_index}/{total_batches}")
                batch = tweets_for_triage[i : i + batch_size]
                future = text_pool.submit(triage_tweets_batch, batch, triage_model, None)
                batch_futures[future] = (batch_index, len(batch))

            for future in as_completed(batch_futures):
                batch_index, batch_size_count = batch_futures[future]
                if status_cb:
                    status_cb(f"Scored batch {batch_index}/{total_batches}")
                try:
                    results = future.result()
                except Exception:
                    if status_cb:
                        status_cb(f"Batch {batch_index} failed")
                    if progress_cb:
                        progress_cb(batch_size_count)
                    results = []
                all_results.extend(results)
                if results:
                    _handle_results(results)
        else:
            for i in range(0, total, batch_size):
                batch_index = (i // batch_size) + 1
                if status_cb:
                    status_cb(f"Scoring batch {batch_index}/{total_batches}")
                batch = tweets_for_triage[i : i + batch_size]
                results = triage_tweets_batch(batch, model=triage_model)
                all_results.extend(results)
                _handle_results(results)

        for future in as_completed(list(summary_futures.keys())):
            tweet_id = summary_futures.pop(future)
            try:
                content_summary = future.result()
                if content_summary:
                    update_tweet_enrichment(
                        conn,
                        tweet_id=tweet_id,
                        content_summary=content_summary,
                    )
            except Exception:
                pass
            _complete_task(tweet_id)

        for future in as_completed(list(media_futures.keys())):
            tweet_id = media_futures.pop(future)
            try:
                updated_items, _ = future.result()
                media_summary = build_media_summary(updated_items)
                update_tweet_enrichment(
                    conn,
                    tweet_id=tweet_id,
                    media_analysis=media_summary,
                    media_items=updated_items,
                )
            except Exception:
                pass
            _complete_task(tweet_id)

        if enrich_candidates:
            for tweet_id in list(enrich_candidates):
                row = get_tweet_by_id(conn, tweet_id)
                if not row or row["analysis_json"]:
                    _complete_task(tweet_id)
                    continue

                quoted_text = ""
                if row["has_quote"] and row["quote_tweet_id"]:
                    quoted_row = get_tweet_by_id(conn, row["quote_tweet_id"])
                    if quoted_row:
                        quoted_text = f"@{quoted_row['author_handle']}: {quoted_row['content']}"

                media_items = parse_media_items(row["media_items"])
                media_context = build_media_context(media_items) if media_items else (row["media_analysis"] or "")

                acct_cursor = conn.execute(
                    "SELECT category FROM accounts WHERE handle = ?",
                    (row["author_handle"],),
                )
                acct_row = acct_cursor.fetchone()
                author_category = acct_row["category"] if acct_row else "unknown"

                if status_cb:
                    status_cb(f"Enriching @{row['author_handle']}")

                if text_pool:
                    future = text_pool.submit(
                        enrich_tweet,
                        tweet_text=row["content"],
                        handle=row["author_handle"],
                        author_category=author_category or "unknown",
                        quoted_tweet=quoted_text,
                        article_summary=row["link_summary"] or "",
                        image_description=media_context,
                        model=enrich_model,
                    )
                    enrich_futures[future] = (tweet_id, row)
                else:
                    try:
                        result = enrich_tweet(
                            tweet_text=row["content"],
                            handle=row["author_handle"],
                            author_category=author_category or "unknown",
                            quoted_tweet=quoted_text,
                            article_summary=row["link_summary"] or "",
                            image_description=media_context,
                            model=enrich_model,
                        )
                        analysis_payload = {
                            "signal_tier": result.signal_tier,
                            "insight": result.insight,
                            "implications": result.implications,
                            "narratives": result.narratives,
                            "tickers": result.tickers,
                            "analyzed_at": datetime.now(timezone.utc).isoformat(),
                        }
                        existing_tickers: list[str] = []
                        if row["tickers"]:
                            try:
                                existing_tickers = json.loads(row["tickers"])
                            except json.JSONDecodeError:
                                existing_tickers = [t.strip() for t in row["tickers"].split(",") if t.strip()]
                        merged_tickers = existing_tickers
                        if result.tickers:
                            merged_tickers = sorted(set(existing_tickers + result.tickers))
                        update_tweet_analysis(
                            conn,
                            tweet_id=tweet_id,
                            analysis=analysis_payload,
                            signal_tier=result.signal_tier or row["signal_tier"],
                            tickers=merged_tickers,
                        )
                    except Exception:
                        pass
                    _complete_task(tweet_id)

            for future in as_completed(list(enrich_futures.keys())):
                tweet_id, row = enrich_futures.pop(future)
                try:
                    result = future.result()
                    analysis_payload = {
                        "signal_tier": result.signal_tier,
                        "insight": result.insight,
                        "implications": result.implications,
                        "narratives": result.narratives,
                        "tickers": result.tickers,
                        "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    }
                    existing_tickers: list[str] = []
                    if row["tickers"]:
                        try:
                            existing_tickers = json.loads(row["tickers"])
                        except json.JSONDecodeError:
                            existing_tickers = [t.strip() for t in row["tickers"].split(",") if t.strip()]
                    merged_tickers = existing_tickers
                    if result.tickers:
                        merged_tickers = sorted(set(existing_tickers + result.tickers))
                    update_tweet_analysis(
                        conn,
                        tweet_id=tweet_id,
                        analysis=analysis_payload,
                        signal_tier=result.signal_tier or row["signal_tier"],
                        tickers=merged_tickers,
                    )
                except Exception:
                    pass
                _complete_task(tweet_id)
    finally:
        if text_pool:
            text_pool.shutdown(wait=True)
        if vision_pool:
            vision_pool.shutdown(wait=True)

    return all_results


def reprocess_today_quoted(
    limit: int = 200,
    min_score: float | None = None,
    dry_run: bool = False,
    triage_model: str | None = None,
    rows: list[sqlite3.Row] | None = None,
    progress_cb: Callable[[int], None] | None = None,
    status_cb: Callable[[str], None] | None = None,
) -> list[TriageResult]:
    """Reprocess today's already-processed tweets that include quotes."""
    config = load_config()
    batch_size = config["scoring"]["batch_size"]
    high_threshold = config["scoring"]["high_signal_threshold"]
    min_score = min_score if min_score is not None else config["scoring"].get("min_score_for_reprocess", 3)

    today = datetime.now().strftime("%Y-%m-%d")

    with get_connection() as conn:
        if rows is None:
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

        conn.commit()

    return results


def enrich_high_signal(
    limit: int = 10,
    enrich_model: str | None = None,
) -> list[EnrichmentResult]:
    """Enrich high-signal tweets with deeper analysis."""
    config = load_config()
    high_threshold = config["scoring"]["high_signal_threshold"]
    max_text_workers = config.get("llm", {}).get("max_concurrency_text", 8)

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

        results: list[EnrichmentResult] = []
        futures = {}
        text_pool = ThreadPoolExecutor(max_workers=max_text_workers) if max_text_workers and max_text_workers > 1 else None

        try:
            for tweet in tweets:
                quoted_text = ""
                if tweet["has_quote"] and tweet["quote_tweet_id"]:
                    # Try to fetch quoted tweet
                    quoted = read_tweet(tweet["quote_tweet_id"])
                    if quoted:
                        quoted_text = f"@{quoted.author_handle}: {quoted.content}"

                media_items = ensure_media_analysis(conn, tweet)
                media_context = build_media_context(media_items) if media_items else (tweet["media_analysis"] or "")

                # Get account category
                acct_cursor = conn.execute(
                    "SELECT category FROM accounts WHERE handle = ?",
                    (tweet["author_handle"],),
                )
                acct_row = acct_cursor.fetchone()
                author_category = acct_row["category"] if acct_row else "unknown"

                if text_pool:
                    future = text_pool.submit(
                        enrich_tweet,
                        tweet_text=tweet["content"],
                        handle=tweet["author_handle"],
                        author_category=author_category or "unknown",
                        quoted_tweet=quoted_text,
                        article_summary=tweet["link_summary"] or "",
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
                        article_summary=tweet["link_summary"] or "",
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


def fetch_and_store_bookmarks(count: int = 100) -> tuple[int, int]:
    """Fetch bookmarks and store/mark them. Returns (fetched, new) counts."""
    tweets = fetch_bookmarks(count=count)
    return store_bookmarked_tweets(tweets)


def auto_promote_bookmarked_authors(min_bookmarks: int = 3) -> list[str]:
    """Promote authors with enough bookmarks to tier-1. Returns promoted handles."""
    promoted = []

    with get_connection() as conn:
        authors = get_authors_to_promote(conn, min_bookmarks=min_bookmarks)

        for handle in authors:
            promote_account(conn, handle)
            promoted.append(handle)

        conn.commit()

    return promoted


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
            from .db import get_accounts

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
