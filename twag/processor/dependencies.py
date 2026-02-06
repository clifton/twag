"""Dependency resolution: fetch/expand quote chains, reply chains, inline links."""

from __future__ import annotations

import json
import sqlite3
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from ..db import (
    get_tweet_by_id,
    get_tweets_by_ids,
    insert_tweet,
    is_tweet_seen,
    update_tweet_links_expanded,
    upsert_account,
)
from ..fetcher import Tweet, read_tweet
from ..link_utils import expand_links_in_place, parse_tweet_status_id

_MAX_INLINE_LINK_FETCHES = 4


def _row_get(row: sqlite3.Row | dict[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(row, sqlite3.Row):
        try:
            return row[key]
        except (IndexError, KeyError):
            return default
    return row.get(key, default)


def _extract_inline_linked_tweet_ids_from_links_json(
    links_json: str | None, *, skip_id: str | None = None
) -> list[str]:
    if not links_json:
        return []
    try:
        decoded = json.loads(links_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []

    ids: list[str] = []
    seen: set[str] = set()
    for link in decoded:
        if not isinstance(link, dict):
            continue
        expanded = str(link.get("expanded_url") or link.get("expandedUrl") or "").strip()
        raw = str(link.get("url") or "").strip()
        linked_id = parse_tweet_status_id(expanded) or parse_tweet_status_id(raw)
        if not linked_id:
            continue
        if skip_id and linked_id == skip_id:
            continue
        if linked_id in seen:
            continue
        seen.add(linked_id)
        ids.append(linked_id)
        if len(ids) >= _MAX_INLINE_LINK_FETCHES:
            break
    return ids


def _extract_dependency_ids_from_row(row: sqlite3.Row | dict[str, Any]) -> list[str]:
    """Return direct dependency tweet IDs for a row."""
    tweet_id = str(_row_get(row, "id", "") or "").strip() or None

    ordered: list[str] = []
    seen: set[str] = set()

    def _add(candidate: str | None) -> None:
        if not candidate:
            return
        value = str(candidate).strip()
        if not value:
            return
        if tweet_id and value == tweet_id:
            return
        if value in seen:
            return
        seen.add(value)
        ordered.append(value)

    _add(_row_get(row, "quote_tweet_id"))
    _add(_row_get(row, "in_reply_to_tweet_id"))
    for linked_id in _extract_inline_linked_tweet_ids_from_links_json(_row_get(row, "links_json"), skip_id=tweet_id):
        _add(linked_id)
    return ordered


def _expand_single_tweet_links(row: sqlite3.Row | dict[str, Any]) -> tuple[str, list[dict[str, Any]] | None]:
    """Expand URL entities for one tweet row."""
    tweet_id = str(row["id"])
    raw_links = row["links_json"]
    if not raw_links:
        return tweet_id, None
    try:
        decoded = json.loads(raw_links)
    except json.JSONDecodeError:
        return tweet_id, None
    if not isinstance(decoded, list):
        return tweet_id, None
    link_items = [item for item in decoded if isinstance(item, dict)]
    if not link_items:
        return tweet_id, []
    return tweet_id, expand_links_in_place(link_items)


def _expand_links_for_rows(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row] | list[dict[str, Any]],
    *,
    max_workers: int,
    quote_depth: int,
    status_cb: Callable[[str], None] | None = None,
) -> list[sqlite3.Row | dict[str, Any]]:
    """Expand link entities for rows and dependency rows, then refresh source rows."""
    if not rows:
        return rows

    source_ids: list[str] = []
    for row in rows:
        tweet_id = str(_row_get(row, "id", "") or "").strip()
        if tweet_id:
            source_ids.append(tweet_id)
    if not source_ids:
        return rows

    source_id_set = set(source_ids)
    row_cache = get_tweets_by_ids(conn, source_id_set)
    all_ids = set(row_cache.keys())
    frontier = {
        dep_id
        for row in row_cache.values()
        for dep_id in _extract_dependency_ids_from_row(row)
        if dep_id not in all_ids
    }

    for _ in range(max(0, quote_depth)):
        if not frontier:
            break
        fetched = get_tweets_by_ids(conn, frontier)
        if not fetched:
            break
        row_cache.update(fetched)
        all_ids.update(fetched.keys())
        frontier = {
            dep_id
            for row in fetched.values()
            for dep_id in _extract_dependency_ids_from_row(row)
            if dep_id not in all_ids
        }

    rows_for_link_expansion = [
        row for row in row_cache.values() if row["has_link"] and row["links_json"] and not row["links_expanded_at"]
    ]
    if rows_for_link_expansion:
        if status_cb:
            status_cb(f"Expanding links for {len(rows_for_link_expansion)} tweets")

        row_by_id = {str(row["id"]): row for row in rows_for_link_expansion}
        expanded_at = datetime.now(timezone.utc).isoformat()

        if max_workers > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(_expand_single_tweet_links, row): str(row["id"]) for row in rows_for_link_expansion
                }
                for future in as_completed(futures):
                    tweet_id = futures[future]
                    original_row = row_by_id[tweet_id]
                    try:
                        _, expanded_links = future.result()
                    except Exception:
                        expanded_links = None
                    links_payload: list[dict[str, Any]] | str | None = (
                        expanded_links if expanded_links is not None else original_row["links_json"]
                    )
                    update_tweet_links_expanded(conn, tweet_id, links_payload, expanded_at)
        else:
            for row in rows_for_link_expansion:
                tweet_id = str(row["id"])
                try:
                    _, expanded_links = _expand_single_tweet_links(row)
                except Exception:
                    expanded_links = None
                links_payload = expanded_links if expanded_links is not None else row["links_json"]
                update_tweet_links_expanded(conn, tweet_id, links_payload, expanded_at)

    refreshed_source = get_tweets_by_ids(conn, source_id_set)
    refreshed_rows: list[sqlite3.Row | dict[str, Any]] = []
    for row in rows:
        tweet_id = str(_row_get(row, "id", "") or "").strip()
        if tweet_id and tweet_id in refreshed_source:
            refreshed_rows.append(refreshed_source[tweet_id])
        else:
            refreshed_rows.append(row)
    return refreshed_rows


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


def _fetch_reply_chain(
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
    if not tweet.in_reply_to_tweet_id:
        return 0
    return _fetch_quote_by_id(
        conn,
        tweet.in_reply_to_tweet_id,
        source=source,
        remaining_depth=max_depth,
        delay=delay,
        seen=seen,
        status_cb=status_cb,
    )


def _extract_inline_linked_tweet_ids(tweet: Tweet) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for link in tweet.links or []:
        if not isinstance(link, dict):
            continue
        expanded = str(link.get("expanded_url") or "").strip()
        raw = str(link.get("url") or "").strip()
        linked_id = parse_tweet_status_id(expanded) or parse_tweet_status_id(raw)
        if not linked_id:
            continue
        if linked_id == tweet.id:
            continue
        if tweet.quote_tweet_id and linked_id == tweet.quote_tweet_id:
            continue
        if linked_id in seen:
            continue
        seen.add(linked_id)
        ids.append(linked_id)
        if len(ids) >= _MAX_INLINE_LINK_FETCHES:
            break
    return ids


def _fetch_inline_linked_tweets(
    conn: sqlite3.Connection,
    tweet: Tweet,
    *,
    source: str,
    delay: float,
    seen: set[str],
    status_cb: Callable[[str], None] | None = None,
) -> int:
    total = 0
    for linked_id in _extract_inline_linked_tweet_ids(tweet):
        total += _fetch_quote_by_id(
            conn,
            linked_id,
            source=source,
            remaining_depth=1,
            delay=delay,
            seen=seen,
            status_cb=status_cb,
        )
    return total


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
        status_cb(f"Fetching dependency tweet {quote_id}")

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
        in_reply_to_tweet_id=quoted.in_reply_to_tweet_id,
        conversation_id=quoted.conversation_id,
        has_media=quoted.has_media,
        media_items=quoted.media_items,
        has_link=quoted.has_link,
        links=quoted.links,
        is_x_article=quoted.is_x_article,
        article_title=quoted.article_title,
        article_preview=quoted.article_preview,
        article_text=quoted.article_text,
        is_retweet=quoted.is_retweet,
        retweeted_by_handle=quoted.retweeted_by_handle,
        retweeted_by_name=quoted.retweeted_by_name,
        original_tweet_id=quoted.original_tweet_id,
        original_author_handle=quoted.original_author_handle,
        original_author_name=quoted.original_author_name,
        original_content=quoted.original_content,
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
    if quoted.in_reply_to_tweet_id:
        total += _fetch_quote_by_id(
            conn,
            quoted.in_reply_to_tweet_id,
            source="reply_parent",
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
        status_cb(f"Fetching dependency tweet {quote_id}")

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
        source="dependency",
        has_quote=quoted.has_quote,
        quote_tweet_id=quoted.quote_tweet_id,
        in_reply_to_tweet_id=quoted.in_reply_to_tweet_id,
        conversation_id=quoted.conversation_id,
        has_media=quoted.has_media,
        media_items=quoted.media_items,
        has_link=quoted.has_link,
        links=quoted.links,
        is_x_article=quoted.is_x_article,
        article_title=quoted.article_title,
        article_preview=quoted.article_preview,
        article_text=quoted.article_text,
        is_retweet=quoted.is_retweet,
        retweeted_by_handle=quoted.retweeted_by_handle,
        retweeted_by_name=quoted.retweeted_by_name,
        original_tweet_id=quoted.original_tweet_id,
        original_author_handle=quoted.original_author_handle,
        original_author_name=quoted.original_author_name,
        original_content=quoted.original_content,
    )
    if inserted:
        upsert_account(conn, quoted.author_handle, quoted.author_name)

    return get_tweet_by_id(conn, quoted.id)


def _expand_unprocessed_with_dependencies(
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
    seen_dependency_ids: set[str] = set()

    queue: deque[tuple[sqlite3.Row, int]] = deque((row, 0) for row in rows)

    while queue:
        row, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for dep_id in _extract_dependency_ids_from_row(row):
            if dep_id in seen_dependency_ids:
                continue
            seen_dependency_ids.add(dep_id)

            dep_row = get_tweet_by_id(conn, dep_id)
            if not dep_row and fetch_missing:
                dep_row = _ensure_quote_row(conn, dep_id, delay=delay, status_cb=status_cb)
            if not dep_row:
                continue

            queue.append((dep_row, depth + 1))

            if dep_row["processed_at"] is None and dep_id not in process_ids:
                process_ids.add(dep_id)
                expanded.append(dep_row)
                if total_cb:
                    total_cb(len(expanded))

    return expanded
