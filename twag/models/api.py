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


# --- Reaction response models ---


class ReactionCreateResponse(BaseModel):
    """Response from creating a reaction."""

    id: int | None = None
    tweet_id: str | None = None
    reaction_type: str | None = None
    message: str | None = None
    error: str | None = None


class ReactionItem(BaseModel):
    """A single reaction entry."""

    id: int
    reaction_type: str
    reason: str | None = None
    target: str | None = None
    created_at: str | None = None


class TweetReactionsResponse(BaseModel):
    """Reactions for a specific tweet."""

    tweet_id: str
    reactions: list[ReactionItem] = []


class ReactionDeleteResponse(BaseModel):
    """Response from deleting a reaction."""

    message: str | None = None
    error: str | None = None


class ReactionSummaryResponse(BaseModel):
    """Summary of reaction counts."""

    summary: dict[str, int] = {}


class ExportReactionDetail(BaseModel):
    """Reaction detail in export."""

    id: int
    type: str
    reason: str | None = None
    created_at: str | None = None


class ExportTweetDetail(BaseModel):
    """Tweet detail in export."""

    id: str
    author: str
    content: str | None = None
    summary: str | None = None
    score: float | None = None
    categories: list[str] = []
    signal_tier: str | None = None


class ExportReactionItem(BaseModel):
    """A reaction-tweet pair in export."""

    reaction: ExportReactionDetail
    tweet: ExportTweetDetail


class ReactionExportResponse(BaseModel):
    """Response from exporting reactions."""

    count: int = 0
    reactions: list[ExportReactionItem] = []


# --- Prompt response models ---


class PromptResponse(BaseModel):
    """A single prompt."""

    id: int | None = None
    name: str | None = None
    template: str | None = None
    version: int | None = None
    updated_at: str | None = None
    updated_by: str | None = None
    error: str | None = None


class PromptListResponse(BaseModel):
    """List of prompts."""

    prompts: list[PromptResponse] = []


class PromptUpdateResponse(BaseModel):
    """Response from updating a prompt."""

    name: str | None = None
    version: int | None = None
    message: str | None = None
    error: str | None = None


class PromptHistoryResponse(BaseModel):
    """Version history for a prompt."""

    name: str
    history: list[dict[str, Any]] = []


class PromptRollbackResponse(BaseModel):
    """Response from rolling back a prompt."""

    message: str | None = None
    error: str | None = None


class PromptTuneResponse(BaseModel):
    """Response from prompt tuning."""

    prompt_name: str | None = None
    current_version: int | None = None
    analysis: str | None = None
    suggested_prompt: str | None = None
    reactions_analyzed: dict[str, int] | None = None
    error: str | None = None


# --- Context command response models ---


class ContextCommandItem(BaseModel):
    """A single context command."""

    id: int | None = None
    name: str | None = None
    command_template: str | None = None
    description: str | None = None
    enabled: bool | None = None
    created_at: str | None = None
    error: str | None = None


class ContextCommandListResponse(BaseModel):
    """List of context commands."""

    commands: list[ContextCommandItem] = []


class ContextCommandCreateResponse(BaseModel):
    """Response from creating a context command."""

    id: int | None = None
    name: str | None = None
    message: str | None = None
    error: str | None = None


class ContextCommandDeleteResponse(BaseModel):
    """Response from deleting a context command."""

    message: str | None = None
    error: str | None = None


class ContextCommandToggleResponse(BaseModel):
    """Response from toggling a context command."""

    message: str | None = None
    error: str | None = None


class CategoriesResponse(BaseModel):
    """List of categories with counts."""

    categories: list[CategoryCount] = []


class TickersResponse(BaseModel):
    """List of tickers with counts."""

    tickers: list[TickerCount] = []


class SingleTweetResponse(BaseModel):
    """Single tweet detail (from /tweets/{id} endpoint)."""

    id: str | None = None
    author_handle: str | None = None
    author_name: str | None = None
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
    links_json: str | None = None
    error: str | None = None


# Rebuild QuoteEmbed to resolve the self-reference
QuoteEmbed.model_rebuild()
