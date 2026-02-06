"""Pydantic models for FastAPI response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class QuoteEmbed(BaseModel):
    """A quoted tweet embed."""

    id: str
    author_handle: str
    author_name: str | None = None
    content: str | None = None
    created_at: str | None = None
    quote_embed: QuoteEmbed | None = None


class CategoryCount(BaseModel):
    """A category with its tweet count."""

    name: str
    count: int


class TickerCount(BaseModel):
    """A ticker symbol with its mention count."""

    symbol: str
    count: int


class TweetResponse(BaseModel):
    """A single tweet in API responses."""

    id: str
    author_handle: str
    author_name: str | None = None
    display_author_handle: str | None = None
    display_author_name: str | None = None
    display_tweet_id: str | None = None
    content: str | None = None
    content_summary: str | None = None
    summary: str | None = None
    created_at: str | None = None
    relevance_score: float | None = None
    categories: list[str] = []
    signal_tier: str | None = None
    tickers: list[str] = []
    bookmarked: bool = False
    has_quote: bool = False
    quote_tweet_id: str | None = None
    has_media: bool = False
    media_analysis: str | None = None
    media_items: list[dict[str, Any]] = []
    has_link: bool = False
    link_summary: str | None = None
    is_x_article: bool = False
    article_title: str | None = None
    article_preview: str | None = None
    article_text: str | None = None
    article_summary_short: str | None = None
    article_primary_points: list[dict[str, Any]] = []
    article_action_items: list[dict[str, Any]] = []
    article_top_visual: dict[str, Any] | None = None
    article_processed_at: str | None = None
    is_retweet: bool = False
    retweeted_by_handle: str | None = None
    retweeted_by_name: str | None = None
    original_tweet_id: str | None = None
    original_author_handle: str | None = None
    original_author_name: str | None = None
    original_content: str | None = None
    reactions: list[str] = []
    quote_embed: QuoteEmbed | None = None
    inline_quote_embeds: list[QuoteEmbed] = []
    reference_links: list[dict[str, str]] = []
    external_links: list[dict[str, str]] = []
    display_content: str | None = None


class TweetListResponse(BaseModel):
    """Paginated list of tweets."""

    tweets: list[TweetResponse] = []
    offset: int = 0
    limit: int = 50
    count: int = 0
    has_more: bool = False


# Rebuild QuoteEmbed to resolve the self-reference
QuoteEmbed.model_rebuild()
