"""Pydantic models for database query results."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — Pydantic needs this at runtime
from typing import Any

from pydantic import BaseModel


class SearchResult(BaseModel):
    """A tweet search result with relevance ranking."""

    id: str
    author_handle: str
    author_name: str | None = None
    content: str = ""
    summary: str | None = None
    created_at: datetime | None = None
    relevance_score: float | None = None
    categories: list[str] = []
    signal_tier: str | None = None
    tickers: list[str] = []
    bookmarked: bool = False
    rank: float = 0.0


class Reaction(BaseModel):
    """A user reaction to a tweet."""

    id: int
    tweet_id: str
    reaction_type: str
    reason: str | None = None
    target: str | None = None
    created_at: datetime | None = None


class Prompt(BaseModel):
    """An editable LLM prompt template."""

    id: int
    name: str
    template: str
    version: int = 1
    updated_at: datetime | None = None
    updated_by: str | None = None


class ContextCommand(BaseModel):
    """A CLI command for fetching context during analysis."""

    id: int
    name: str
    command_template: str
    description: str | None = None
    enabled: bool = True
    created_at: datetime | None = None


class FeedTweet(BaseModel):
    """A tweet for the web feed with all display fields."""

    id: str
    author_handle: str
    author_name: str | None = None
    content: str = ""
    content_summary: str | None = None
    summary: str | None = None
    created_at: datetime | None = None
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
    links: list[dict[str, Any]] = []
    link_summary: str | None = None
    is_x_article: bool = False
    article_title: str | None = None
    article_preview: str | None = None
    article_text: str | None = None
    article_summary_short: str | None = None
    article_primary_points: list[dict[str, Any]] = []
    article_action_items: list[dict[str, Any]] = []
    article_top_visual: dict[str, Any] | None = None
    article_processed_at: datetime | None = None
    is_retweet: bool = False
    retweeted_by_handle: str | None = None
    retweeted_by_name: str | None = None
    original_tweet_id: str | None = None
    original_author_handle: str | None = None
    original_author_name: str | None = None
    original_content: str | None = None
    reactions: list[str] = []
