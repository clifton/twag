"""Tweet CRUD operations."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def insert_tweet(
    conn: sqlite3.Connection,
    tweet_id: str,
    author_handle: str,
    content: str,
    created_at: datetime | None = None,
    author_name: str | None = None,
    source: str = "home",
    has_quote: bool = False,
    quote_tweet_id: str | None = None,
    in_reply_to_tweet_id: str | None = None,
    conversation_id: str | None = None,
    has_media: bool = False,
    media_items: list[dict[str, Any]] | None = None,
    has_link: bool = False,
    is_x_article: bool = False,
    article_title: str | None = None,
    article_preview: str | None = None,
    article_text: str | None = None,
    is_retweet: bool = False,
    retweeted_by_handle: str | None = None,
    retweeted_by_name: str | None = None,
    original_tweet_id: str | None = None,
    original_author_handle: str | None = None,
    original_author_name: str | None = None,
    original_content: str | None = None,
    links: list[dict[str, Any]] | None = None,
) -> bool:
    """Insert a tweet, returning True if new, False if duplicate."""
    try:
        conn.execute(
            """
            INSERT INTO tweets (
                id, author_handle, author_name, content, created_at, source,
                has_quote, quote_tweet_id, in_reply_to_tweet_id, conversation_id, has_media, media_items, has_link,
                links_json,
                is_x_article, article_title, article_preview, article_text,
                is_retweet, retweeted_by_handle, retweeted_by_name, original_tweet_id,
                original_author_handle, original_author_name, original_content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tweet_id,
                author_handle,
                author_name,
                content,
                created_at.isoformat() if created_at else None,
                source,
                int(has_quote),
                quote_tweet_id,
                in_reply_to_tweet_id,
                conversation_id,
                int(has_media),
                json.dumps(media_items) if media_items else None,
                int(has_link),
                json.dumps(links) if links else None,
                int(is_x_article),
                article_title,
                article_preview,
                article_text,
                int(is_retweet),
                retweeted_by_handle,
                retweeted_by_name,
                original_tweet_id,
                original_author_handle,
                original_author_name,
                original_content,
            ),
        )
        return True
    except sqlite3.IntegrityError:
        _merge_duplicate_tweet_payload(
            conn,
            tweet_id=tweet_id,
            author_name=author_name,
            content=content,
            created_at=created_at,
            has_quote=has_quote,
            quote_tweet_id=quote_tweet_id,
            in_reply_to_tweet_id=in_reply_to_tweet_id,
            conversation_id=conversation_id,
            has_media=has_media,
            media_items=media_items,
            has_link=has_link,
            links=links,
            is_x_article=is_x_article,
            article_title=article_title,
            article_preview=article_preview,
            article_text=article_text,
        )
        _merge_duplicate_retweet_metadata(
            conn,
            tweet_id=tweet_id,
            is_retweet=is_retweet,
            retweeted_by_handle=retweeted_by_handle,
            retweeted_by_name=retweeted_by_name,
            original_tweet_id=original_tweet_id,
            original_author_handle=original_author_handle,
            original_author_name=original_author_name,
            original_content=original_content,
        )
        return False


def _merge_media_items(
    existing_json: str | None,
    incoming_items: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if not incoming_items:
        return None

    existing_items: list[dict[str, Any]] = []
    if existing_json:
        try:
            decoded = json.loads(existing_json)
            if isinstance(decoded, list):
                existing_items = [i for i in decoded if isinstance(i, dict)]
        except json.JSONDecodeError:
            existing_items = []

    by_url: dict[str, dict[str, Any]] = {}
    for item in existing_items + incoming_items:
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        if url in by_url:
            by_url[url].update({k: v for k, v in item.items() if v is not None})
        else:
            by_url[url] = dict(item)

    merged = list(by_url.values())
    return merged if merged else None


def _merge_duplicate_tweet_payload(
    conn: sqlite3.Connection,
    *,
    tweet_id: str,
    author_name: str | None,
    content: str,
    created_at: datetime | None,
    has_quote: bool,
    quote_tweet_id: str | None,
    in_reply_to_tweet_id: str | None,
    conversation_id: str | None,
    has_media: bool,
    media_items: list[dict[str, Any]] | None,
    has_link: bool,
    links: list[dict[str, Any]] | None,
    is_x_article: bool,
    article_title: str | None,
    article_preview: str | None,
    article_text: str | None,
) -> None:
    """Backfill richer non-retweet fields on duplicate inserts."""
    row = conn.execute(
        """
        SELECT author_name, content, created_at, has_quote, quote_tweet_id, has_media, media_items,
               in_reply_to_tweet_id, conversation_id, links_json,
               has_link, is_x_article, article_title, article_preview, article_text
        FROM tweets
        WHERE id = ?
        """,
        (tweet_id,),
    ).fetchone()
    if row is None:
        return

    updates: list[str] = []
    params: list[Any] = []

    existing_content = row["content"] or ""
    incoming_content = content or ""
    if incoming_content and (
        not existing_content
        or _looks_truncated_text(existing_content)
        or len(incoming_content.strip()) >= len(existing_content.strip()) + 120
    ):
        updates.append("content = ?")
        params.append(incoming_content)

    if author_name and not row["author_name"]:
        updates.append("author_name = ?")
        params.append(author_name)

    if created_at and not row["created_at"]:
        updates.append("created_at = ?")
        params.append(created_at.isoformat())

    if has_quote and not row["has_quote"]:
        updates.append("has_quote = 1")
    if quote_tweet_id and not row["quote_tweet_id"]:
        updates.append("quote_tweet_id = ?")
        params.append(quote_tweet_id)

    if in_reply_to_tweet_id and not row["in_reply_to_tweet_id"]:
        updates.append("in_reply_to_tweet_id = ?")
        params.append(in_reply_to_tweet_id)

    if conversation_id and not row["conversation_id"]:
        updates.append("conversation_id = ?")
        params.append(conversation_id)

    merged_media = _merge_media_items(row["media_items"], media_items)
    if merged_media is not None:
        existing_media_len = 0
        if row["media_items"]:
            try:
                parsed = json.loads(row["media_items"])
                if isinstance(parsed, list):
                    existing_media_len = len(parsed)
            except json.JSONDecodeError:
                existing_media_len = 0
        if len(merged_media) > existing_media_len:
            updates.append("media_items = ?")
            params.append(json.dumps(merged_media))
            updates.append("has_media = 1")
        elif has_media and not row["has_media"]:
            updates.append("has_media = 1")
    elif has_media and not row["has_media"]:
        updates.append("has_media = 1")

    if has_link and not row["has_link"]:
        updates.append("has_link = 1")

    merged_links = _merge_media_items(row["links_json"], links)
    if merged_links is not None:
        existing_link_len = 0
        if row["links_json"]:
            try:
                parsed = json.loads(row["links_json"])
                if isinstance(parsed, list):
                    existing_link_len = len(parsed)
            except json.JSONDecodeError:
                existing_link_len = 0
        if len(merged_links) > existing_link_len:
            updates.append("links_json = ?")
            params.append(json.dumps(merged_links))
            updates.append("links_expanded_at = NULL")

    if is_x_article and not row["is_x_article"]:
        updates.append("is_x_article = 1")

    existing_title = (row["article_title"] or "").strip()
    incoming_title = (article_title or "").strip()
    if incoming_title and (not existing_title or len(incoming_title) > len(existing_title)):
        updates.append("article_title = ?")
        params.append(incoming_title)

    existing_preview = (row["article_preview"] or "").strip()
    incoming_preview = (article_preview or "").strip()
    if incoming_preview and (not existing_preview or len(incoming_preview) > len(existing_preview)):
        updates.append("article_preview = ?")
        params.append(incoming_preview)

    existing_article_text = (row["article_text"] or "").strip()
    incoming_article_text = (article_text or "").strip()
    if incoming_article_text and (
        not existing_article_text
        or _looks_truncated_text(existing_article_text)
        or len(incoming_article_text) >= len(existing_article_text) + 120
    ):
        updates.append("article_text = ?")
        params.append(incoming_article_text)

    if not updates:
        return

    params.append(tweet_id)
    conn.execute(f"UPDATE tweets SET {', '.join(updates)} WHERE id = ?", params)


def _looks_truncated_text(text: str | None) -> bool:
    if not text:
        return False
    stripped = text.rstrip()
    return bool(stripped) and (stripped.endswith("\u2026") or stripped.endswith("..."))


def _merge_duplicate_retweet_metadata(
    conn: sqlite3.Connection,
    *,
    tweet_id: str,
    is_retweet: bool,
    retweeted_by_handle: str | None,
    retweeted_by_name: str | None,
    original_tweet_id: str | None,
    original_author_handle: str | None,
    original_author_name: str | None,
    original_content: str | None,
) -> None:
    """Backfill retweet metadata on duplicate inserts when new payload is richer."""
    if not is_retweet:
        return

    updates = ["is_retweet = CASE WHEN is_retweet = 0 THEN 1 ELSE is_retweet END"]
    params: list[Any] = []

    def _coalesce_if_present(column: str, value: str | None) -> None:
        if value is None:
            return
        updates.append(f"{column} = COALESCE({column}, ?)")
        params.append(value)

    _coalesce_if_present("retweeted_by_handle", retweeted_by_handle)
    _coalesce_if_present("retweeted_by_name", retweeted_by_name)
    _coalesce_if_present("original_tweet_id", original_tweet_id)
    _coalesce_if_present("original_author_handle", original_author_handle)
    _coalesce_if_present("original_author_name", original_author_name)

    if original_content and not _looks_truncated_text(original_content):
        existing_row = conn.execute(
            "SELECT original_content FROM tweets WHERE id = ?",
            (tweet_id,),
        ).fetchone()
        existing_original = existing_row["original_content"] if existing_row else None
        if _should_replace_original_content(existing_original, original_content):
            updates.append("original_content = ?")
            params.append(original_content)

    params.append(tweet_id)
    conn.execute(f"UPDATE tweets SET {', '.join(updates)} WHERE id = ?", params)


def _should_replace_original_content(existing: str | None, candidate: str) -> bool:
    if not candidate or _looks_truncated_text(candidate):
        return False
    if not existing or not existing.strip():
        return True
    if _looks_truncated_text(existing):
        return True
    existing_stripped = existing.rstrip()
    candidate_stripped = candidate.rstrip()
    if len(candidate_stripped) > len(existing_stripped) and candidate_stripped.startswith(existing_stripped):
        return True
    return False


def get_unprocessed_tweets(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    """Get tweets that haven't been processed yet."""
    cursor = conn.execute(
        """
        SELECT * FROM tweets
        WHERE processed_at IS NULL
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    return cursor.fetchall()


def update_tweet_processing(
    conn: sqlite3.Connection,
    tweet_id: str,
    relevance_score: float,
    categories: list[str] | str,
    summary: str,
    signal_tier: str,
    tickers: list[str] | None = None,
) -> None:
    """Update a tweet with processing results."""
    # Normalize categories to list and store as JSON
    if isinstance(categories, str):
        categories = [categories]

    conn.execute(
        """
        UPDATE tweets SET
            processed_at = ?,
            relevance_score = ?,
            category = ?,
            summary = ?,
            signal_tier = ?,
            tickers = ?
        WHERE id = ?
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            relevance_score,
            json.dumps(categories),
            summary,
            signal_tier,
            json.dumps(tickers) if tickers else None,
            tweet_id,
        ),
    )


def update_tweet_enrichment(
    conn: sqlite3.Connection,
    tweet_id: str,
    media_analysis: str | None = None,
    media_items: list[dict[str, Any]] | None = None,
    link_summary: str | None = None,
    content_summary: str | None = None,
) -> None:
    """Update a tweet with enrichment data."""
    updates = []
    params = []

    if media_analysis is not None:
        updates.append("media_analysis = ?")
        params.append(media_analysis)

    if media_items is not None:
        updates.append("media_items = ?")
        params.append(json.dumps(media_items))

    if link_summary is not None:
        updates.append("link_summary = ?")
        params.append(link_summary)

    if content_summary is not None:
        updates.append("content_summary = ?")
        params.append(content_summary)

    if updates:
        params.append(tweet_id)
        conn.execute(
            f"UPDATE tweets SET {', '.join(updates)} WHERE id = ?",
            params,
        )


def update_tweet_links_expanded(
    conn: sqlite3.Connection,
    tweet_id: str,
    links_json: list[dict[str, Any]] | str | None,
    expanded_at: str,
) -> None:
    """Persist normalized links payload and expansion timestamp."""
    if isinstance(links_json, str) or links_json is None:
        payload = links_json
    else:
        payload = json.dumps(links_json)
    conn.execute(
        """
        UPDATE tweets SET
            links_json = ?,
            links_expanded_at = ?
        WHERE id = ?
        """,
        (payload, expanded_at, tweet_id),
    )


def update_tweet_article(
    conn: sqlite3.Connection,
    tweet_id: str,
    *,
    article_summary_short: str | None = None,
    primary_points: list[dict[str, Any]] | None = None,
    actionable_items: list[dict[str, Any]] | None = None,
    top_visual: dict[str, Any] | None = None,
    set_top_visual: bool = False,
    processed_at: str | None = None,
    mirror_to_link_summary: bool = True,
) -> None:
    """Update structured X article analysis fields for a tweet."""
    updates: list[str] = []
    params: list[Any] = []

    if article_summary_short is not None:
        updates.append("article_summary_short = ?")
        params.append(article_summary_short)
        if mirror_to_link_summary:
            updates.append("link_summary = ?")
            params.append(article_summary_short)

    if primary_points is not None:
        updates.append("article_primary_points_json = ?")
        params.append(json.dumps(primary_points))

    if actionable_items is not None:
        updates.append("article_action_items_json = ?")
        params.append(json.dumps(actionable_items))

    if set_top_visual:
        updates.append("article_top_visual_json = ?")
        params.append(json.dumps(top_visual) if top_visual else None)

    if processed_at is not None:
        updates.append("article_processed_at = ?")
        params.append(processed_at)

    if not updates:
        return

    params.append(tweet_id)
    conn.execute(
        f"UPDATE tweets SET {', '.join(updates)} WHERE id = ?",
        params,
    )


def update_tweet_analysis(
    conn: sqlite3.Connection,
    tweet_id: str,
    analysis: dict[str, Any],
    signal_tier: str | None = None,
    tickers: list[str] | None = None,
) -> None:
    """Store structured analysis results for a tweet."""
    updates = ["analysis_json = ?"]
    params: list[Any] = [json.dumps(analysis)]

    if signal_tier is not None:
        updates.append("signal_tier = ?")
        params.append(signal_tier)

    if tickers is not None:
        updates.append("tickers = ?")
        params.append(json.dumps(tickers) if tickers else None)

    params.append(tweet_id)
    conn.execute(
        f"UPDATE tweets SET {', '.join(updates)} WHERE id = ?",
        params,
    )


def get_tweets_for_digest(
    conn: sqlite3.Connection,
    date: str,
    min_score: float = 5.0,
) -> list[sqlite3.Row]:
    """Get processed tweets for a specific date above min_score."""
    cursor = conn.execute(
        """
        SELECT * FROM tweets
        WHERE date(created_at) = ?
        AND relevance_score >= ?
        AND processed_at IS NOT NULL
        ORDER BY relevance_score DESC
        """,
        (date, min_score),
    )
    return cursor.fetchall()


def mark_tweet_in_digest(conn: sqlite3.Connection, tweet_id: str, date: str) -> None:
    """Mark a tweet as included in a digest."""
    conn.execute(
        "UPDATE tweets SET included_in_digest = ? WHERE id = ?",
        (date, tweet_id),
    )


def is_tweet_seen(conn: sqlite3.Connection, tweet_id: str) -> bool:
    """Check if a tweet has been seen before."""
    cursor = conn.execute("SELECT 1 FROM tweets WHERE id = ?", (tweet_id,))
    return cursor.fetchone() is not None


def get_tweet_stats(conn: sqlite3.Connection, date: str | None = None) -> dict[str, Any]:
    """Get tweet processing statistics."""
    if date:
        where_clause = "WHERE date(created_at) = ?"
        params: tuple = (date,)
    else:
        where_clause = ""
        params = ()

    cursor = conn.execute(
        f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN processed_at IS NOT NULL THEN 1 ELSE 0 END) as processed,
            SUM(CASE WHEN processed_at IS NULL THEN 1 ELSE 0 END) as pending,
            AVG(relevance_score) as avg_score,
            SUM(CASE WHEN relevance_score >= 7 THEN 1 ELSE 0 END) as high_signal,
            SUM(CASE WHEN relevance_score >= 5 THEN 1 ELSE 0 END) as digest_worthy
        FROM tweets
        {where_clause}
        """,
        params,
    )
    row = cursor.fetchone()
    return dict(row) if row else {}


def get_processed_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Get counts of tweets processed in recent time windows.

    Returns:
        Dict with keys '1h', '24h', '7d' containing tweet counts.
    """
    cursor = conn.execute(
        """
        SELECT
            SUM(CASE WHEN processed_at >= datetime('now', '-1 hour') THEN 1 ELSE 0 END) as last_1h,
            SUM(CASE WHEN processed_at >= datetime('now', '-24 hours') THEN 1 ELSE 0 END) as last_24h,
            SUM(CASE WHEN processed_at >= datetime('now', '-7 days') THEN 1 ELSE 0 END) as last_7d
        FROM tweets
        WHERE processed_at IS NOT NULL
        """
    )
    row = cursor.fetchone()
    if row:
        return {
            "1h": row["last_1h"] or 0,
            "24h": row["last_24h"] or 0,
            "7d": row["last_7d"] or 0,
        }
    return {"1h": 0, "24h": 0, "7d": 0}


def mark_tweet_bookmarked(conn: sqlite3.Connection, tweet_id: str) -> None:
    """Mark a tweet as bookmarked."""
    conn.execute(
        """
        UPDATE tweets SET
            bookmarked = 1,
            bookmarked_at = COALESCE(bookmarked_at, ?)
        WHERE id = ?
        """,
        (datetime.now(timezone.utc).isoformat(), tweet_id),
    )


def get_bookmark_counts_by_author(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Get count of bookmarked tweets per author."""
    cursor = conn.execute(
        """
        SELECT author_handle, COUNT(*) as bookmark_count
        FROM tweets
        WHERE bookmarked = 1
        GROUP BY author_handle
        ORDER BY bookmark_count DESC
        """
    )
    return [(row[0], row[1]) for row in cursor.fetchall()]


def get_authors_to_promote(conn: sqlite3.Connection, min_bookmarks: int = 3) -> list[str]:
    """Get authors with enough bookmarks to promote to tier-1."""
    cursor = conn.execute(
        """
        SELECT t.author_handle
        FROM tweets t
        LEFT JOIN accounts a ON t.author_handle = a.handle
        WHERE t.bookmarked = 1
        AND (a.tier IS NULL OR a.tier > 1)
        GROUP BY t.author_handle
        HAVING COUNT(*) >= ?
        """,
        (min_bookmarks,),
    )
    return [row[0] for row in cursor.fetchall()]


def get_tweet_by_id(conn: sqlite3.Connection, tweet_id: str) -> sqlite3.Row | None:
    """Get a single tweet by ID."""
    cursor = conn.execute("SELECT * FROM tweets WHERE id = ?", (tweet_id,))
    return cursor.fetchone()


def get_tweets_by_ids(conn: sqlite3.Connection, tweet_ids: set[str]) -> dict[str, sqlite3.Row]:
    """Batch-fetch tweets by IDs. Returns {id: Row} dict.

    Handles SQLite's 999-parameter limit by chunking.
    """
    if not tweet_ids:
        return {}

    result: dict[str, sqlite3.Row] = {}
    id_list = list(tweet_ids)
    chunk_size = 999

    for i in range(0, len(id_list), chunk_size):
        chunk = id_list[i : i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        cursor = conn.execute(
            f"SELECT * FROM tweets WHERE id IN ({placeholders})",
            chunk,
        )
        for row in cursor.fetchall():
            result[row["id"]] = row

    return result


def log_fetch(
    conn: sqlite3.Connection,
    endpoint: str,
    tweets_fetched: int,
    new_tweets: int,
    query_params: dict | None = None,
) -> None:
    """Log a fetch operation."""
    conn.execute(
        """
        INSERT INTO fetch_log (endpoint, tweets_fetched, new_tweets, query_params)
        VALUES (?, ?, ?, ?)
        """,
        (endpoint, tweets_fetched, new_tweets, json.dumps(query_params)),
    )


def get_last_fetch(conn: sqlite3.Connection, endpoint: str) -> sqlite3.Row | None:
    """Get the last fetch for an endpoint."""
    cursor = conn.execute(
        """
        SELECT * FROM fetch_log
        WHERE endpoint = ?
        ORDER BY executed_at DESC
        LIMIT 1
        """,
        (endpoint,),
    )
    return cursor.fetchone()


def migrate_seen_json(conn: sqlite3.Connection, seen_json_path: Path) -> int:
    """Migrate seen.json to database. Returns count of migrated IDs."""
    if not seen_json_path.exists():
        return 0

    with open(seen_json_path) as f:
        data = json.load(f)

    seen_ids = data.get("seen", [])
    count = 0

    for tweet_id in seen_ids:
        try:
            conn.execute(
                """
                INSERT INTO tweets (id, author_handle, content, source)
                VALUES (?, ?, ?, ?)
                """,
                (tweet_id, "unknown", "[migrated from seen.json]", "migration"),
            )
            count += 1
        except sqlite3.IntegrityError:
            pass  # Already exists

    return count
