"""Tweet storage: persist fetched/bookmarked tweets with dependency chains."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..config import load_config
from ..db import (
    get_authors_to_promote,
    get_connection,
    insert_tweet,
    log_fetch,
    mark_tweet_bookmarked,
    promote_account,
    upsert_account,
)
from ..fetcher import (
    Tweet,
    fetch_bookmarks,
    fetch_home_timeline,
    fetch_search,
    fetch_user_tweets,
)
from .dependencies import (
    _fetch_inline_linked_tweets,
    _fetch_quote_chain,
    _fetch_reply_chain,
)


def _store_tweets(
    tweets: list[Tweet],
    conn,
    *,
    bookmarked: bool = False,
    source: str = "home",
    quote_depth: int = 0,
    quote_delay: float = 1.0,
    query_params: dict[str, Any] | None = None,
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[int], None] | None = None,
) -> tuple[int, int]:
    """Unified storage for fetched/bookmarked tweets."""
    fetched = len(tweets)
    new_count = 0
    seen_quotes: set[str] = set()

    for tweet in tweets:
        if not tweet.id:
            if progress_cb:
                progress_cb(1)
            continue

        if status_cb:
            label = f"Storing bookmark @{tweet.author_handle}" if bookmarked else f"Storing @{tweet.author_handle}"
            status_cb(label)

        effective_source = "bookmarks" if bookmarked else source

        inserted = insert_tweet(
            conn,
            tweet_id=tweet.id,
            author_handle=tweet.author_handle,
            author_name=tweet.author_name,
            content=tweet.content,
            created_at=tweet.created_at,
            source=effective_source,
            has_quote=tweet.has_quote,
            quote_tweet_id=tweet.quote_tweet_id,
            in_reply_to_tweet_id=tweet.in_reply_to_tweet_id,
            conversation_id=tweet.conversation_id,
            has_media=tweet.has_media,
            media_items=tweet.media_items,
            has_link=tweet.has_link,
            links=tweet.links,
            is_x_article=tweet.is_x_article,
            article_title=tweet.article_title,
            article_preview=tweet.article_preview,
            article_text=tweet.article_text,
            is_retweet=tweet.is_retweet,
            retweeted_by_handle=tweet.retweeted_by_handle,
            retweeted_by_name=tweet.retweeted_by_name,
            original_tweet_id=tweet.original_tweet_id,
            original_author_handle=tweet.original_author_handle,
            original_author_name=tweet.original_author_name,
            original_content=tweet.original_content,
        )

        if inserted:
            new_count += 1

        if bookmarked:
            mark_tweet_bookmarked(conn, tweet.id)
            upsert_account(conn, tweet.author_handle, tweet.author_name)
        else:
            if inserted:
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
            _fetch_reply_chain(
                conn,
                tweet,
                source="reply_parent",
                max_depth=quote_depth,
                delay=quote_delay,
                seen=seen_quotes,
                status_cb=status_cb,
            )

        if inserted:
            _fetch_inline_linked_tweets(
                conn,
                tweet,
                source="inline_link",
                delay=quote_delay,
                seen=seen_quotes,
                status_cb=status_cb,
            )

        if progress_cb:
            progress_cb(1)

    log_fetch(
        conn,
        endpoint=("bookmarks" if bookmarked else source),
        tweets_fetched=fetched,
        new_tweets=new_count,
        query_params=query_params or {},
    )
    conn.commit()

    return fetched, new_count


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

    with get_connection() as conn:
        return _store_tweets(
            tweets,
            conn,
            bookmarked=False,
            source=source,
            quote_depth=quote_depth,
            quote_delay=quote_delay,
            query_params=query_params,
            status_cb=status_cb,
            progress_cb=progress_cb,
        )


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

    with get_connection() as conn:
        return _store_tweets(
            tweets,
            conn,
            bookmarked=True,
            quote_depth=quote_depth,
            quote_delay=quote_delay,
            status_cb=status_cb,
            progress_cb=progress_cb,
        )


def fetch_and_store(
    source: str = "home",
    handle: str | None = None,
    query: str | None = None,
    count: int = 100,
) -> tuple[int, int]:
    """Fetch tweets and store new ones. Returns (fetched, new) counts."""
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
