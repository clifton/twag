"""Triage/processing passes: scoring, media analysis, article summarization."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from ..config import load_config
from ..db import (
    get_tweet_by_id,
    update_account_stats,
    update_tweet_analysis,
    update_tweet_article,
    update_tweet_enrichment,
    update_tweet_processing,
)
from ..media import build_media_context, build_media_summary, parse_media_items
from ..scorer import (
    TriageResult,
    analyze_media,
    enrich_tweet,
    summarize_document_text,
    summarize_tweet,
    summarize_x_article,
    triage_tweets_batch,
)

_SIGNAL_TIER_RANK = {
    "noise": 0,
    "news": 1,
    "market_relevant": 2,
    "high_signal": 3,
}


def _normalized_worker_count(value: Any, fallback: int) -> int:
    """Return a positive worker count, falling back on invalid inputs."""
    try:
        workers = int(value)
    except (TypeError, ValueError):
        workers = fallback
    return workers if workers > 0 else fallback


def _prefer_stronger_signal_tier(existing: str | None, candidate: str | None) -> str | None:
    """Return the stronger signal tier, defaulting to existing when equal/unknown."""
    if not existing and not candidate:
        return None
    if not existing:
        return candidate
    if not candidate:
        return existing

    existing_rank = _SIGNAL_TIER_RANK.get(str(existing), -1)
    candidate_rank = _SIGNAL_TIER_RANK.get(str(candidate), -1)
    return candidate if candidate_rank > existing_rank else existing


def _build_triage_text(tweet_row: sqlite3.Row) -> str:
    """Build triage text, favoring article body for X-native articles."""
    content = (tweet_row["content"] or "").strip()
    if not tweet_row["is_x_article"]:
        return content

    article_text = (tweet_row["article_text"] or "").strip()
    if not article_text:
        return content

    title = (tweet_row["article_title"] or "").strip()
    preview = (tweet_row["article_preview"] or "").strip()
    parts = [part for part in [title, preview, article_text] if part]
    combined = "\n\n".join(parts)

    # Keep triage payload bounded while preserving rich article context.
    if len(combined) > 6000:
        combined = combined[:6000]

    # Prefer article-aware text when materially richer than tweet content.
    if not content or len(combined) >= len(content) + 120:
        return combined
    return content


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


def _tokenize_for_overlap(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-zA-Z]{3,}", text.lower()) if tok}


def _select_article_top_visual(
    media_items: list[dict[str, Any]],
    *,
    article_title: str = "",
    article_summary: str = "",
    primary_points: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Select top visual only if it is chart/table or highly relevant evidence."""
    context_parts = [article_title, article_summary]
    for point in primary_points or []:
        if not isinstance(point, dict):
            continue
        context_parts.append(str(point.get("point", "")))
        context_parts.append(str(point.get("reasoning", "")))
        context_parts.append(str(point.get("evidence", "")))
    context_text = " ".join(part for part in context_parts if part)
    context_tokens = _tokenize_for_overlap(context_text)

    best: tuple[float, dict[str, Any]] | None = None
    for item in media_items:
        url = item.get("url")
        if not url:
            continue

        kind = (item.get("kind") or "").strip().lower()
        chart = item.get("chart") if isinstance(item.get("chart"), dict) else {}
        table = item.get("table") if isinstance(item.get("table"), dict) else {}

        chart_text = " ".join(
            [
                str(chart.get("description", "")),
                str(chart.get("insight", "")),
                str(chart.get("implication", "")),
            ]
        ).strip()
        table_text = " ".join(
            [
                str(table.get("title", "")),
                str(table.get("description", "")),
                str(table.get("summary", "")),
            ]
        ).strip()
        prose_text = " ".join(
            [
                str(item.get("prose_summary", "")),
                str(item.get("short_description", "")),
                str(item.get("prose_text", "")),
            ]
        ).strip()
        candidate_text = " ".join(part for part in [chart_text, table_text, prose_text] if part).strip()
        if not candidate_text:
            continue

        if kind in {"meme", "photo", "other", ""}:
            continue

        has_numbers = bool(re.search(r"\d", candidate_text))
        overlap = len(_tokenize_for_overlap(candidate_text) & context_tokens) if context_tokens else 0

        # Gate non-chart visuals heavily to avoid irrelevant picks.
        if kind in {"document", "screenshot"} and (overlap < 2 or not has_numbers):
            continue
        if kind not in {"chart", "table", "document", "screenshot"}:
            continue
        if kind in {"chart", "table"} and overlap == 0 and not has_numbers:
            continue

        base = 100.0 if kind in {"chart", "table"} else 70.0
        score = base + (10.0 if has_numbers else 0.0) + float(overlap * 5)

        takeaway = ""
        if kind == "chart":
            takeaway = str(chart.get("insight") or chart.get("description") or "").strip()
        elif kind == "table":
            takeaway = str(table.get("summary") or table.get("description") or "").strip()
        if not takeaway:
            takeaway = str(item.get("prose_summary") or item.get("short_description") or "").strip()
        if not takeaway:
            continue

        visual = {
            "url": url,
            "kind": kind,
            "why_important": "Most relevant quantitative visual supporting the article thesis.",
            "key_takeaway": takeaway,
        }
        if best is None or score > best[0]:
            best = (score, visual)

    return best[1] if best else None


def _process_article(
    media_items: list[dict[str, Any]],
    *,
    vision_model: str | None,
    vision_provider: str | None,
    article_text: str,
    article_title: str,
    article_preview: str,
    enrich_model: str | None,
) -> tuple[Any, list[dict[str, Any]]]:
    """Analyze media then summarize article — runs in text_pool thread."""
    analyzed_items, _ = _analyze_media_items(
        media_items,
        vision_model=vision_model,
        vision_provider=vision_provider,
    )
    article_result = summarize_x_article(
        article_text,
        article_title=article_title,
        article_preview=article_preview,
        model=enrich_model,
        provider=None,
    )
    return article_result, analyzed_items


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
    force_refresh: bool = False,
) -> list[TriageResult]:
    """Run triage on provided rows and persist results."""
    config = load_config()
    max_text_workers = _normalized_worker_count(config.get("llm", {}).get("max_concurrency_text", 5), 5)
    max_triage_workers = _normalized_worker_count(
        config.get("llm", {}).get("max_concurrency_triage", max_text_workers),
        max_text_workers,
    )
    max_vision_workers = _normalized_worker_count(config.get("llm", {}).get("max_concurrency_vision", 3), 3)
    vision_model = config["llm"].get("vision_model")
    vision_provider = config["llm"].get("vision_provider")
    analysis_min_score = config.get("scoring", {}).get("min_score_for_analysis", 3)
    article_min_score = config.get("scoring", {}).get("min_score_for_article_processing", 5)
    tweets_for_triage = []
    tweet_map: dict[str, sqlite3.Row] = {}

    for row in tweet_rows:
        tweet_id = row["id"]
        tweets_for_triage.append(
            {
                "id": tweet_id,
                "text": _build_triage_text(row),
                "handle": row["author_handle"],
            }
        )
        tweet_map[tweet_id] = row

    all_results: list[TriageResult] = []

    total = len(tweets_for_triage)
    total_batches = (total + batch_size - 1) // batch_size

    pending_tasks: dict[str, int] = {}

    # Unified future map: Future -> (tag, data)
    # Tags: "summary", "media", "article", "enrich"
    all_futures: dict[Any, tuple[str, Any]] = {}

    triage_pool = ThreadPoolExecutor(max_workers=max_triage_workers) if max_triage_workers > 1 else None
    text_pool = ThreadPoolExecutor(max_workers=max_text_workers) if max_text_workers and max_text_workers > 1 else None
    vision_pool = (
        ThreadPoolExecutor(max_workers=max_vision_workers) if max_vision_workers and max_vision_workers > 1 else None
    )

    def _complete_task(tweet_id: str) -> None:
        if tweet_id not in pending_tasks:
            return
        pending_tasks[tweet_id] -= 1
        if pending_tasks[tweet_id] <= 0:
            pending_tasks.pop(tweet_id, None)
            if progress_cb:
                progress_cb(1)

    def _submit_enrichment(tweet_id: str, tweet_row: sqlite3.Row) -> None:
        """Prepare enrichment parameters (fast DB reads) and submit to text_pool."""
        row = get_tweet_by_id(conn, tweet_id)
        if not row or (row["analysis_json"] and not force_refresh):
            _complete_task(tweet_id)
            return

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
                article_summary=row["article_summary_short"] or row["link_summary"] or "",
                image_description=media_context,
                model=enrich_model,
            )
            all_futures[future] = ("enrich", (tweet_id, row))
        else:
            try:
                result = enrich_tweet(
                    tweet_text=row["content"],
                    handle=row["author_handle"],
                    author_category=author_category or "unknown",
                    quoted_tweet=quoted_text,
                    article_summary=row["article_summary_short"] or row["link_summary"] or "",
                    image_description=media_context,
                    model=enrich_model,
                )
                _save_enrichment_result(conn, tweet_id, row, result)
            except Exception:
                pass
            _complete_task(tweet_id)

    def _submit_article(tweet_id: str, tweet_row: sqlite3.Row) -> None:
        """Prepare article processing and submit to text_pool."""
        row = get_tweet_by_id(conn, tweet_id)
        if not row or (row["article_processed_at"] and not force_refresh):
            _complete_task(tweet_id)
            return

        article_text = (row["article_text"] or row["content"] or "").strip()
        if not article_text and not row["article_preview"] and not row["article_title"]:
            _complete_task(tweet_id)
            return

        media_items = parse_media_items(row["media_items"]) if row["has_media"] else []

        if status_cb:
            status_cb(f"Summarizing article @{row['author_handle']}")

        if text_pool:
            if media_items and _needs_media_analysis(media_items):
                # Use wrapper that analyzes media then summarizes article
                future = text_pool.submit(
                    _process_article,
                    media_items,
                    vision_model=vision_model,
                    vision_provider=vision_provider,
                    article_text=article_text,
                    article_title=row["article_title"] or "",
                    article_preview=row["article_preview"] or "",
                    enrich_model=enrich_model,
                )
            else:
                # Media already analyzed or no media — just summarize
                future = text_pool.submit(
                    lambda at, atitle, aprev, em, mi: (
                        summarize_x_article(at, article_title=atitle, article_preview=aprev, model=em, provider=None),
                        mi,
                    ),
                    article_text,
                    row["article_title"] or "",
                    row["article_preview"] or "",
                    enrich_model,
                    media_items,
                )
            all_futures[future] = ("article", (tweet_id, row))
        else:
            try:
                if media_items and _needs_media_analysis(media_items):
                    media_items, _ = _analyze_media_items(
                        media_items, vision_model=vision_model, vision_provider=vision_provider
                    )
                article_result = summarize_x_article(
                    article_text,
                    article_title=row["article_title"] or "",
                    article_preview=row["article_preview"] or "",
                    model=enrich_model,
                )
                top_visual = _select_article_top_visual(
                    media_items,
                    article_title=row["article_title"] or "",
                    article_summary=article_result.short_summary,
                    primary_points=article_result.primary_points,
                )
                update_tweet_article(
                    conn,
                    tweet_id,
                    article_summary_short=article_result.short_summary,
                    primary_points=article_result.primary_points,
                    actionable_items=article_result.actionable_items,
                    top_visual=top_visual,
                    set_top_visual=True,
                    processed_at=datetime.now(timezone.utc).isoformat(),
                )
                # Persist analyzed media if updated
                if media_items:
                    media_summary = build_media_summary(media_items)
                    update_tweet_enrichment(
                        conn,
                        tweet_id=tweet_id,
                        media_analysis=media_summary,
                        media_items=media_items,
                    )
            except Exception:
                pass
            _complete_task(tweet_id)

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
                    all_futures[future] = ("summary", result.tweet_id)
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
                        all_futures[future] = ("media", result.tweet_id)
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
                and (force_refresh or not tweet_row["analysis_json"])
            )
            if needs_analysis:
                task_count += 1

            needs_article = (
                tweet_row is not None
                and bool(tweet_row["is_x_article"])
                and (force_refresh or not tweet_row["article_processed_at"])
                and result.score >= article_min_score
                and bool(tweet_row["article_text"] or tweet_row["article_preview"] or tweet_row["article_title"])
            )
            if needs_article:
                task_count += 1

            if task_count:
                pending_tasks[result.tweet_id] = task_count
            else:
                if progress_cb:
                    progress_cb(1)

            # Submit enrichment and article immediately (after pending_tasks is set)
            if needs_analysis:
                _submit_enrichment(result.tweet_id, tweet_row)
            if needs_article:
                _submit_article(result.tweet_id, tweet_row)

    try:
        if triage_pool:
            batch_futures: dict[Any, tuple[int, int]] = {}
            for i in range(0, total, batch_size):
                batch_index = (i // batch_size) + 1
                if status_cb:
                    status_cb(f"Queue batch {batch_index}/{total_batches}")
                batch = tweets_for_triage[i : i + batch_size]
                future = triage_pool.submit(triage_tweets_batch, batch, triage_model, None)
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

        # Unified collection: all downstream futures complete in natural order
        for future in as_completed(list(all_futures.keys())):
            tag, data = all_futures.pop(future)
            if tag == "summary":
                tweet_id = data
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
            elif tag == "media":
                tweet_id = data
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
            elif tag == "article":
                tweet_id, row = data
                try:
                    article_result, analyzed_items = future.result()
                    top_visual = _select_article_top_visual(
                        analyzed_items,
                        article_title=row["article_title"] or "",
                        article_summary=article_result.short_summary,
                        primary_points=article_result.primary_points,
                    )
                    update_tweet_article(
                        conn,
                        tweet_id,
                        article_summary_short=article_result.short_summary,
                        primary_points=article_result.primary_points,
                        actionable_items=article_result.actionable_items,
                        top_visual=top_visual,
                        set_top_visual=True,
                        processed_at=datetime.now(timezone.utc).isoformat(),
                    )
                    if analyzed_items:
                        media_summary = build_media_summary(analyzed_items)
                        update_tweet_enrichment(
                            conn,
                            tweet_id=tweet_id,
                            media_analysis=media_summary,
                            media_items=analyzed_items,
                        )
                except Exception:
                    pass
                _complete_task(tweet_id)
            elif tag == "enrich":
                tweet_id, row = data
                try:
                    result = future.result()
                    _save_enrichment_result(conn, tweet_id, row, result)
                except Exception:
                    pass
                _complete_task(tweet_id)
    finally:
        if triage_pool:
            triage_pool.shutdown(wait=True)
        if text_pool:
            text_pool.shutdown(wait=True)
        if vision_pool:
            vision_pool.shutdown(wait=True)

    return all_results


def _save_enrichment_result(
    conn: sqlite3.Connection,
    tweet_id: str,
    row: sqlite3.Row,
    result: Any,
) -> None:
    """Persist enrichment result to DB."""
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
        signal_tier=_prefer_stronger_signal_tier(row["signal_tier"], result.signal_tier),
        tickers=merged_tickers,
    )
