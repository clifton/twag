"""Tweet feed API routes."""

import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, Request

from ...db import get_connection, get_feed_tweets, get_tweet_by_id, parse_time_range
from ...media import parse_media_items
from ..tweet_utils import extract_tweet_links, quote_embed_from_row, remove_tweet_links

router = APIRouter(tags=["tweets"])
MAX_QUOTE_DEPTH = 3
LEGACY_RETWEET_RE = re.compile(r"^\s*RT\s+@([A-Za-z0-9_]{1,15}):\s*(.+)$")


def _inline_quote_id_from_links(tweet_id: str, links: dict[str, str]) -> str | None:
    for linked_tweet_id in links:
        if linked_tweet_id and linked_tweet_id != tweet_id:
            return linked_tweet_id
    return None


def _looks_truncated_text(text: str | None) -> bool:
    if not text:
        return False
    stripped = text.rstrip()
    return bool(stripped) and (stripped.endswith("\u2026") or stripped.endswith("..."))


def _build_quote_embed(
    conn, quote_id: str | None, *, depth: int = 0, seen: set[str] | None = None
) -> dict[str, Any] | None:
    if not quote_id:
        return None
    if depth >= MAX_QUOTE_DEPTH:
        return None

    visited = seen or set()
    if quote_id in visited:
        return None
    visited.add(quote_id)

    row = get_tweet_by_id(conn, quote_id)
    if not row:
        return None

    embed = quote_embed_from_row(row)

    content = row["content"] or ""
    links = extract_tweet_links(content)
    link_map: dict[str, str] = {}
    for linked_tweet_id, linked_url in links:
        if linked_tweet_id and linked_tweet_id not in link_map:
            link_map[linked_tweet_id] = linked_url

    nested_quote_id = row["quote_tweet_id"] or _inline_quote_id_from_links(row["id"], link_map)
    if nested_quote_id and nested_quote_id != row["id"]:
        nested_embed = _build_quote_embed(conn, nested_quote_id, depth=depth + 1, seen=visited)
        if nested_embed:
            embed["quote_embed"] = nested_embed

    return embed


@router.get("/tweets")
async def list_tweets(
    request: Request,
    category: str | None = None,
    ticker: str | None = None,
    min_score: float | None = Query(None, ge=0, le=10),
    signal_tier: str | None = None,
    author: str | None = None,
    bookmarked: bool = False,
    since: str | None = None,
    until: str | None = None,
    sort: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """
    Get paginated feed of processed tweets.

    Filters:
    - category: Filter by category (fed_policy, equities, etc.)
    - ticker: Filter by ticker symbol
    - min_score: Minimum relevance score (0-10)
    - signal_tier: Filter by signal tier (high_signal, market_relevant, news, noise)
    - author: Filter by author handle
    - bookmarked: Only show bookmarked tweets
    - since: Time range start ("today", "7d", "2025-01-15", etc.)
    - until: Time range end (YYYY-MM-DD)
    """
    db_path = request.app.state.db_path

    # Parse time ranges
    since_dt = None
    until_dt = None
    if since:
        since_dt, parsed_until = parse_time_range(since)
        if parsed_until and until is None:
            until_dt = parsed_until
    if until:
        try:
            until_dt = datetime.fromisoformat(until)
        except ValueError:
            pass

    with get_connection(db_path) as conn:
        tweets = get_feed_tweets(
            conn,
            category=category,
            ticker=ticker,
            min_score=min_score,
            signal_tier=signal_tier,
            author=author,
            bookmarked_only=bookmarked,
            since=since_dt,
            until=until_dt,
            order_by=sort or "relevance",
            limit=limit,
            offset=offset,
        )

        # Enrich tweets with quote embeds and display content
        tweets_data = []
        for t in tweets:
            content = t.content or ""
            links = extract_tweet_links(content)
            link_map: dict[str, str] = {}
            for tid, url in links:
                if tid and tid not in link_map:
                    link_map[tid] = url

            # Determine quote tweet
            inline_quote_id = None
            if not t.has_quote:
                inline_quote_id = _inline_quote_id_from_links(t.id, link_map)

            quote_id = t.quote_tweet_id or inline_quote_id
            if quote_id == t.id:
                quote_id = None
            quote_embed = _build_quote_embed(conn, quote_id)

            # Reference links (other tweet URLs that aren't the quote)
            reference_links: list[dict[str, str]] = []
            for tid, url in link_map.items():
                if tid == t.id:
                    continue
                if quote_id and tid == quote_id:
                    continue
                reference_links.append({"id": tid, "url": url})

            # Clean display content
            remove_ids = set(link_map.keys())
            remove_ids.add(t.id)
            display_content = remove_tweet_links(content, links, remove_ids) if content else content

            is_retweet = bool(t.is_retweet)
            retweeted_by_handle = t.retweeted_by_handle
            retweeted_by_name = t.retweeted_by_name
            original_tweet_id = t.original_tweet_id
            original_author_handle = t.original_author_handle
            original_author_name = t.original_author_name
            original_content = t.original_content

            # Legacy rows may store RT-form text without retweet metadata columns populated.
            if not is_retweet:
                match = LEGACY_RETWEET_RE.match(content)
                if match:
                    is_retweet = True
                    retweeted_by_handle = t.author_handle
                    retweeted_by_name = t.author_name
                    original_author_handle = match.group(1)
                    fallback_original = match.group(2).strip() or None
                    if fallback_original and not _looks_truncated_text(fallback_original):
                        original_content = fallback_original

            display_author_handle = original_author_handle if is_retweet and original_author_handle else t.author_handle
            display_author_name = original_author_name if is_retweet and original_author_name else t.author_name
            display_tweet_id = original_tweet_id if is_retweet and original_tweet_id else t.id
            if is_retweet and original_content:
                display_content = original_content

            tweets_data.append(
                {
                    "id": t.id,
                    "author_handle": t.author_handle,
                    "author_name": t.author_name,
                    "display_author_handle": display_author_handle,
                    "display_author_name": display_author_name,
                    "display_tweet_id": display_tweet_id,
                    "content": t.content,
                    "content_summary": t.content_summary,
                    "summary": t.summary,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "relevance_score": t.relevance_score,
                    "categories": t.categories,
                    "signal_tier": t.signal_tier,
                    "tickers": t.tickers,
                    "bookmarked": t.bookmarked,
                    "has_quote": t.has_quote,
                    "quote_tweet_id": t.quote_tweet_id,
                    "has_media": t.has_media,
                    "media_analysis": t.media_analysis,
                    "media_items": t.media_items,
                    "has_link": t.has_link,
                    "link_summary": t.link_summary,
                    "is_x_article": t.is_x_article,
                    "article_title": t.article_title,
                    "article_preview": t.article_preview,
                    "article_text": t.article_text,
                    "article_summary_short": t.article_summary_short,
                    "article_primary_points": t.article_primary_points,
                    "article_action_items": t.article_action_items,
                    "article_top_visual": t.article_top_visual,
                    "article_processed_at": t.article_processed_at.isoformat() if t.article_processed_at else None,
                    "is_retweet": is_retweet,
                    "retweeted_by_handle": retweeted_by_handle,
                    "retweeted_by_name": retweeted_by_name,
                    "original_tweet_id": original_tweet_id,
                    "original_author_handle": original_author_handle,
                    "original_author_name": original_author_name,
                    "original_content": original_content,
                    "reactions": t.reactions,
                    "quote_embed": quote_embed,
                    "reference_links": reference_links,
                    "display_content": display_content,
                }
            )

    return {
        "tweets": tweets_data,
        "offset": offset,
        "limit": limit,
        "count": len(tweets_data),
        "has_more": len(tweets_data) == limit,
    }


@router.get("/tweets/{tweet_id}")
async def get_tweet(request: Request, tweet_id: str) -> dict[str, Any]:
    """Get a single tweet by ID."""
    import json

    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        tweet = get_tweet_by_id(conn, tweet_id)

    if not tweet:
        return {"error": "Tweet not found"}

    # Parse JSON fields
    categories = []
    if tweet["category"]:
        try:
            categories = json.loads(tweet["category"])
            if isinstance(categories, str):
                categories = [categories]
        except json.JSONDecodeError:
            categories = [tweet["category"]]

    tickers = []
    if tweet["tickers"]:
        try:
            tickers = json.loads(tweet["tickers"])
        except json.JSONDecodeError:
            tickers = [t.strip() for t in tweet["tickers"].split(",") if t.strip()]

    article_primary_points = []
    if tweet["article_primary_points_json"]:
        try:
            decoded = json.loads(tweet["article_primary_points_json"])
            if isinstance(decoded, list):
                article_primary_points = [item for item in decoded if isinstance(item, dict)]
        except json.JSONDecodeError:
            article_primary_points = []

    article_action_items = []
    if tweet["article_action_items_json"]:
        try:
            decoded = json.loads(tweet["article_action_items_json"])
            if isinstance(decoded, list):
                article_action_items = [item for item in decoded if isinstance(item, dict)]
        except json.JSONDecodeError:
            article_action_items = []

    article_top_visual = None
    if tweet["article_top_visual_json"]:
        try:
            decoded = json.loads(tweet["article_top_visual_json"])
            if isinstance(decoded, dict):
                article_top_visual = decoded
        except json.JSONDecodeError:
            article_top_visual = None

    return {
        "id": tweet["id"],
        "author_handle": tweet["author_handle"],
        "author_name": tweet["author_name"],
        "content": tweet["content"],
        "content_summary": tweet["content_summary"],
        "summary": tweet["summary"],
        "created_at": tweet["created_at"],
        "relevance_score": tweet["relevance_score"],
        "categories": categories,
        "signal_tier": tweet["signal_tier"],
        "tickers": tickers,
        "bookmarked": bool(tweet["bookmarked"]),
        "has_quote": bool(tweet["has_quote"]),
        "quote_tweet_id": tweet["quote_tweet_id"],
        "has_media": bool(tweet["has_media"]),
        "media_analysis": tweet["media_analysis"],
        "media_items": parse_media_items(tweet["media_items"]),
        "has_link": bool(tweet["has_link"]),
        "link_summary": tweet["link_summary"],
        "is_x_article": bool(tweet["is_x_article"]),
        "article_title": tweet["article_title"],
        "article_preview": tweet["article_preview"],
        "article_text": tweet["article_text"],
        "article_summary_short": tweet["article_summary_short"],
        "article_primary_points": article_primary_points,
        "article_action_items": article_action_items,
        "article_top_visual": article_top_visual,
        "article_processed_at": tweet["article_processed_at"],
        "is_retweet": bool(tweet["is_retweet"]),
        "retweeted_by_handle": tweet["retweeted_by_handle"],
        "retweeted_by_name": tweet["retweeted_by_name"],
        "original_tweet_id": tweet["original_tweet_id"],
        "original_author_handle": tweet["original_author_handle"],
        "original_author_name": tweet["original_author_name"],
        "original_content": tweet["original_content"],
    }


@router.get("/categories")
async def list_categories(request: Request) -> dict[str, Any]:
    """Get list of all categories with tweet counts."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        # Get category distribution
        cursor = conn.execute(
            """
            SELECT category, COUNT(*) as count
            FROM tweets
            WHERE category IS NOT NULL AND processed_at IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
            """
        )
        raw_counts = {row["category"]: row["count"] for row in cursor.fetchall()}

    # Parse and aggregate categories (they may be JSON arrays)
    import json

    category_counts: dict[str, int] = {}
    for cat_raw, count in raw_counts.items():
        try:
            cats = json.loads(cat_raw)
            if isinstance(cats, str):
                cats = [cats]
        except json.JSONDecodeError:
            cats = [cat_raw]

        for cat in cats:
            category_counts[cat] = category_counts.get(cat, 0) + count

    # Sort by count
    sorted_cats = sorted(category_counts.items(), key=lambda x: -x[1])

    return {"categories": [{"name": name, "count": count} for name, count in sorted_cats]}


@router.get("/tickers")
async def list_tickers(request: Request, limit: int = 50) -> dict[str, Any]:
    """Get list of mentioned tickers with counts."""
    import json

    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT tickers
            FROM tweets
            WHERE tickers IS NOT NULL AND processed_at IS NOT NULL
            """
        )
        rows = cursor.fetchall()

    # Aggregate tickers
    ticker_counts: dict[str, int] = {}
    for row in rows:
        try:
            tickers = json.loads(row["tickers"])
        except json.JSONDecodeError:
            tickers = [t.strip() for t in row["tickers"].split(",") if t.strip()]

        for ticker in tickers:
            ticker = ticker.upper()
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1

    # Sort by count and limit
    sorted_tickers = sorted(ticker_counts.items(), key=lambda x: -x[1])[:limit]

    return {"tickers": [{"symbol": symbol, "count": count} for symbol, count in sorted_tickers]}
