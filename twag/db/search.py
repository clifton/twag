"""Search and feed query operations."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .time_utils import parse_time_range


@dataclass
class SearchResult:
    """A tweet search result with relevance ranking."""

    id: str
    author_handle: str
    author_name: str | None
    content: str
    summary: str | None
    created_at: datetime | None
    relevance_score: float | None
    categories: list[str]
    signal_tier: str | None
    tickers: list[str]
    bookmarked: bool
    rank: float  # BM25 rank score (lower is more relevant)


@dataclass
class FeedTweet:
    """A tweet for the web feed with all display fields."""

    id: str
    author_handle: str
    author_name: str | None
    content: str
    content_summary: str | None
    summary: str | None
    created_at: datetime | None
    relevance_score: float | None
    categories: list[str]
    signal_tier: str | None
    tickers: list[str]
    bookmarked: bool
    has_quote: bool
    quote_tweet_id: str | None
    has_media: bool
    media_analysis: str | None
    media_items: list[dict[str, Any]]
    has_link: bool
    links: list[dict[str, Any]]
    link_summary: str | None
    is_x_article: bool
    article_title: str | None
    article_preview: str | None
    article_text: str | None
    article_summary_short: str | None
    article_primary_points: list[dict[str, Any]]
    article_action_items: list[dict[str, Any]]
    article_top_visual: dict[str, Any] | None
    article_processed_at: datetime | None
    is_retweet: bool
    retweeted_by_handle: str | None
    retweeted_by_name: str | None
    original_tweet_id: str | None
    original_author_handle: str | None
    original_author_name: str | None
    original_content: str | None
    reactions: list[str]  # Reaction types for this tweet


# Keywords that suggest equity-relevant context (for auto-today default)
EQUITY_KEYWORDS = {
    "earnings",
    "eps",
    "revenue",
    "guidance",
    "beat",
    "miss",
    "upgrade",
    "downgrade",
    "buy",
    "sell",
    "target",
    "pt",
    "q1",
    "q2",
    "q3",
    "q4",
    "quarterly",
    "results",
    "report",
}


def query_suggests_equity_context(query: str) -> bool:
    """Check if a search query suggests equity-relevant context."""
    query_lower = query.lower()
    return any(kw in query_lower for kw in EQUITY_KEYWORDS)


def search_tweets(
    conn: sqlite3.Connection,
    query: str,
    *,
    category: str | None = None,
    author: str | None = None,
    min_score: float | None = None,
    signal_tier: str | None = None,
    ticker: str | None = None,
    bookmarked_only: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
    time_range: str | None = None,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "rank",
) -> list[SearchResult]:
    """
    Search tweets using FTS5 full-text search.

    Args:
        query: FTS5 query string (supports AND, OR, NOT, phrases, prefixes)
        category: Filter by category (fed_policy, equities, etc.)
        author: Filter by author handle
        min_score: Minimum relevance score
        signal_tier: Filter by signal tier
        ticker: Filter by ticker symbol
        bookmarked_only: Only return bookmarked tweets
        since: Start time (UTC datetime)
        until: End time (UTC datetime)
        time_range: Time range spec ("today", "7d", "2025-01-15", etc.)
        limit: Maximum results to return
        offset: Offset for pagination
        order_by: Sort order - "rank" (BM25), "score" (relevance), "time" (created_at)

    Returns:
        List of SearchResult objects
    """
    # Parse time_range if provided
    if time_range:
        parsed_since, parsed_until = parse_time_range(time_range)
        if parsed_since and since is None:
            since = parsed_since
        if parsed_until and until is None:
            until = parsed_until

    # Build WHERE conditions
    conditions = []
    params: list[Any] = []

    # FTS match
    conditions.append("tweets_fts MATCH ?")
    params.append(query)

    if category:
        # Match category in JSON array (e.g., '["fed_policy", "rates_fx"]')
        # Also support legacy single-value format
        conditions.append("(t.category LIKE ? OR t.category = ?)")
        params.append(f'%"{category}"%')
        params.append(category)

    if author:
        conditions.append("t.author_handle = ?")
        params.append(author.lstrip("@"))

    if min_score is not None:
        conditions.append("t.relevance_score >= ?")
        params.append(min_score)

    if signal_tier:
        conditions.append("t.signal_tier = ?")
        params.append(signal_tier)

    if ticker:
        # Search in JSON array or comma-separated string
        conditions.append("(t.tickers LIKE ? OR t.tickers LIKE ?)")
        params.append(f'%"{ticker.upper()}"%')
        params.append(f"%{ticker.upper()}%")

    if bookmarked_only:
        conditions.append("t.bookmarked = 1")

    if since:
        conditions.append("t.created_at >= ?")
        params.append(since.isoformat())

    if until:
        conditions.append("t.created_at < ?")
        params.append(until.isoformat())

    where_clause = " AND ".join(conditions)

    # Order clause
    if order_by == "score":
        order_clause = "t.relevance_score DESC NULLS LAST"
    elif order_by == "time":
        order_clause = "t.created_at DESC"
    else:  # rank (BM25)
        order_clause = "bm25(tweets_fts)"

    params.extend([limit, offset])

    sql = f"""
        SELECT
            t.id,
            t.author_handle,
            t.author_name,
            t.content,
            t.summary,
            t.created_at,
            t.relevance_score,
            t.category,
            t.signal_tier,
            t.tickers,
            t.bookmarked,
            bm25(tweets_fts) as rank
        FROM tweets_fts
        JOIN tweets t ON tweets_fts.rowid = t.rowid
        WHERE {where_clause}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """

    cursor = conn.execute(sql, params)
    results = []

    for row in cursor.fetchall():
        # Parse tickers from JSON or comma-separated
        tickers_raw = row["tickers"]
        if tickers_raw:
            try:
                tickers = json.loads(tickers_raw)
            except json.JSONDecodeError:
                tickers = [t.strip() for t in tickers_raw.split(",") if t.strip()]
        else:
            tickers = []

        # Parse created_at
        created_at = None
        if row["created_at"]:
            try:
                created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            except ValueError:
                pass

        # Parse categories from JSON array or legacy string
        categories_raw = row["category"]
        if categories_raw:
            try:
                categories = json.loads(categories_raw)
                if isinstance(categories, str):
                    categories = [categories]
            except json.JSONDecodeError:
                categories = [categories_raw]
        else:
            categories = []

        results.append(
            SearchResult(
                id=row["id"],
                author_handle=row["author_handle"],
                author_name=row["author_name"],
                content=row["content"],
                summary=row["summary"],
                created_at=created_at,
                relevance_score=row["relevance_score"],
                categories=categories,
                signal_tier=row["signal_tier"],
                tickers=tickers,
                bookmarked=bool(row["bookmarked"]),
                rank=row["rank"],
            )
        )

    return results


def get_feed_tweets(
    conn: sqlite3.Connection,
    *,
    category: str | None = None,
    ticker: str | None = None,
    min_score: float | None = None,
    signal_tier: str | None = None,
    author: str | None = None,
    bookmarked_only: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
    order_by: str = "relevance",
    limit: int = 50,
    offset: int = 0,
) -> list[FeedTweet]:
    """Get tweets for the web feed with filters."""
    conditions = ["processed_at IS NOT NULL"]
    params: list[Any] = []

    if category:
        conditions.append("(category LIKE ? OR category = ?)")
        params.append(f'%"{category}"%')
        params.append(category)

    if ticker:
        conditions.append("(tickers LIKE ? OR tickers LIKE ?)")
        params.append(f'%"{ticker.upper()}"%')
        params.append(f"%{ticker.upper()}%")

    if min_score is not None:
        conditions.append("relevance_score >= ?")
        params.append(min_score)

    if signal_tier:
        conditions.append("signal_tier = ?")
        params.append(signal_tier)

    if author:
        conditions.append("author_handle = ?")
        params.append(author.lstrip("@"))

    if bookmarked_only:
        conditions.append("bookmarked = 1")

    if since:
        conditions.append("created_at >= ?")
        params.append(since.isoformat())

    if until:
        conditions.append("created_at < ?")
        params.append(until.isoformat())

    where_clause = " AND ".join(conditions)
    params.extend([limit, offset])

    if order_by == "latest":
        inner_order = "created_at DESC"
        outer_order = "t.created_at DESC"
    else:
        inner_order = "relevance_score DESC, created_at DESC"
        outer_order = "t.relevance_score DESC, t.created_at DESC"

    cursor = conn.execute(
        f"""
        SELECT
            t.*,
            GROUP_CONCAT(DISTINCT r.reaction_type) as reaction_types
        FROM (
            SELECT *
            FROM tweets
            WHERE {where_clause}
            ORDER BY {inner_order}
            LIMIT ? OFFSET ?
        ) t
        LEFT JOIN reactions r ON t.id = r.tweet_id
        GROUP BY t.id
        ORDER BY {outer_order}
        """,
        params,
    )

    results = []
    for row in cursor.fetchall():
        # Parse categories
        categories_raw = row["category"]
        if categories_raw:
            try:
                categories = json.loads(categories_raw)
                if isinstance(categories, str):
                    categories = [categories]
            except json.JSONDecodeError:
                categories = [categories_raw]
        else:
            categories = []

        # Parse tickers
        tickers_raw = row["tickers"]
        if tickers_raw:
            try:
                tickers = json.loads(tickers_raw)
            except json.JSONDecodeError:
                tickers = [t.strip() for t in tickers_raw.split(",") if t.strip()]
        else:
            tickers = []

        # Parse created_at
        created_at = None
        if row["created_at"]:
            try:
                created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            except ValueError:
                pass

        # Parse reactions
        reactions = []
        if row["reaction_types"]:
            reactions = row["reaction_types"].split(",")

        # Parse media items
        media_items = []
        if row["media_items"]:
            try:
                media_items = json.loads(row["media_items"])
            except json.JSONDecodeError:
                media_items = []

        links = []
        if row["links_json"]:
            try:
                decoded = json.loads(row["links_json"])
                if isinstance(decoded, list):
                    links = [item for item in decoded if isinstance(item, dict)]
            except json.JSONDecodeError:
                links = []

        article_primary_points: list[dict[str, Any]] = []
        if row["article_primary_points_json"]:
            try:
                decoded = json.loads(row["article_primary_points_json"])
                if isinstance(decoded, list):
                    article_primary_points = [item for item in decoded if isinstance(item, dict)]
            except json.JSONDecodeError:
                article_primary_points = []

        article_action_items: list[dict[str, Any]] = []
        if row["article_action_items_json"]:
            try:
                decoded = json.loads(row["article_action_items_json"])
                if isinstance(decoded, list):
                    article_action_items = [item for item in decoded if isinstance(item, dict)]
            except json.JSONDecodeError:
                article_action_items = []

        article_top_visual: dict[str, Any] | None = None
        if row["article_top_visual_json"]:
            try:
                decoded = json.loads(row["article_top_visual_json"])
                if isinstance(decoded, dict):
                    article_top_visual = decoded
            except json.JSONDecodeError:
                article_top_visual = None

        article_processed_at = None
        if row["article_processed_at"]:
            try:
                article_processed_at = datetime.fromisoformat(row["article_processed_at"].replace("Z", "+00:00"))
            except ValueError:
                article_processed_at = None

        results.append(
            FeedTweet(
                id=row["id"],
                author_handle=row["author_handle"],
                author_name=row["author_name"],
                content=row["content"],
                content_summary=row["content_summary"],
                summary=row["summary"],
                created_at=created_at,
                relevance_score=row["relevance_score"],
                categories=categories,
                signal_tier=row["signal_tier"],
                tickers=tickers,
                bookmarked=bool(row["bookmarked"]),
                has_quote=bool(row["has_quote"]),
                quote_tweet_id=row["quote_tweet_id"],
                has_media=bool(row["has_media"]),
                media_analysis=row["media_analysis"],
                media_items=media_items,
                has_link=bool(row["has_link"]),
                links=links,
                link_summary=row["link_summary"],
                is_x_article=bool(row["is_x_article"]),
                article_title=row["article_title"],
                article_preview=row["article_preview"],
                article_text=row["article_text"],
                article_summary_short=row["article_summary_short"],
                article_primary_points=article_primary_points,
                article_action_items=article_action_items,
                article_top_visual=article_top_visual,
                article_processed_at=article_processed_at,
                is_retweet=bool(row["is_retweet"]),
                retweeted_by_handle=row["retweeted_by_handle"],
                retweeted_by_name=row["retweeted_by_name"],
                original_tweet_id=row["original_tweet_id"],
                original_author_handle=row["original_author_handle"],
                original_author_name=row["original_author_name"],
                original_content=row["original_content"],
                reactions=reactions,
            )
        )

    return results
