"""Pydantic model for parsed tweet data."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — Pydantic needs this at runtime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TweetData(BaseModel):
    """Parsed tweet data — mirrors the fetcher.Tweet dataclass."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    author_handle: str
    author_name: str | None = None
    content: str = ""
    created_at: datetime | None = None
    has_quote: bool = False
    quote_tweet_id: str | None = None
    in_reply_to_tweet_id: str | None = None
    conversation_id: str | None = None
    has_media: bool = False
    media_items: list[dict[str, Any]] = []
    has_link: bool = False
    is_x_article: bool = False
    article_title: str | None = None
    article_preview: str | None = None
    article_text: str | None = None
    is_retweet: bool = False
    retweeted_by_handle: str | None = None
    retweeted_by_name: str | None = None
    original_tweet_id: str | None = None
    original_author_handle: str | None = None
    original_author_name: str | None = None
    original_content: str | None = None
    raw: dict[str, Any] = {}
    links: list[dict[str, str]] = []
