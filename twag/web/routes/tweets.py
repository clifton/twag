"""Tweet feed API routes."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, Request

from ...db import get_connection, get_feed_tweets, get_tweet_by_id, parse_time_range
from ...media import parse_media_items
from ..tweet_utils import extract_tweet_links, quote_embed_from_row, remove_tweet_links

router = APIRouter(tags=["tweets"])


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
                for tid in link_map:
                    if tid and tid != t.id:
                        inline_quote_id = tid
                        break

            quote_id = t.quote_tweet_id or inline_quote_id
            if quote_id == t.id:
                quote_id = None
            quote_row = get_tweet_by_id(conn, quote_id) if quote_id else None
            quote_embed = quote_embed_from_row(quote_row) if quote_row else None

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
            display_content = (
                remove_tweet_links(content, links, remove_ids) if content else content
            )

            tweets_data.append(
                {
                    "id": t.id,
                    "author_handle": t.author_handle,
                    "author_name": t.author_name,
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
