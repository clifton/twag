"""Pydantic models for FastAPI response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# --- Quote / Tweet models ---


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


class CategoryListResponse(BaseModel):
    """List of categories with counts."""

    categories: list[CategoryCount] = []


class TickerListResponse(BaseModel):
    """List of tickers with counts."""

    tickers: list[TickerCount] = []


# --- Reaction models ---


class ReactionDetail(BaseModel):
    """A single reaction."""

    id: int
    reaction_type: str
    reason: str | None = None
    target: str | None = None
    created_at: str | None = None


class ReactionListResponse(BaseModel):
    """Reactions for a specific tweet."""

    tweet_id: str
    reactions: list[ReactionDetail] = []


class ReactionCreateResponse(BaseModel):
    """Response after creating a reaction."""

    id: int
    tweet_id: str
    reaction_type: str
    message: str | None = None


class ReactionSummaryResponse(BaseModel):
    """Summary of reaction counts."""

    summary: dict[str, Any] = {}


class ExportReactionDetail(BaseModel):
    """A reaction in export format."""

    id: int
    type: str
    reason: str | None = None
    created_at: str | None = None


class ExportTweetDetail(BaseModel):
    """A tweet in export format."""

    id: str
    author: str
    content: str
    summary: str | None = None
    score: float | None = None
    categories: list[str] = []
    signal_tier: str | None = None


class ExportReactionItem(BaseModel):
    """A reaction with its associated tweet in export format."""

    reaction: ExportReactionDetail
    tweet: ExportTweetDetail


class ReactionExportResponse(BaseModel):
    """Exported reactions with tweet data."""

    count: int = 0
    reactions: list[ExportReactionItem] = []


# --- Prompt models ---


class PromptResponse(BaseModel):
    """A single prompt."""

    id: int | None = None
    name: str
    template: str
    version: int = 1
    updated_at: str | None = None
    updated_by: str | None = None


class PromptListResponse(BaseModel):
    """List of prompts."""

    prompts: list[PromptResponse] = []


class PromptUpdateResponse(BaseModel):
    """Response after updating a prompt."""

    name: str
    version: int
    message: str


class PromptHistoryResponse(BaseModel):
    """Version history for a prompt."""

    name: str
    history: list[dict[str, Any]] = []


class PromptTuneResponse(BaseModel):
    """Response from prompt tuning."""

    prompt_name: str
    current_version: int
    analysis: str
    suggested_prompt: str
    reactions_analyzed: dict[str, int] = {}


# --- Context command models ---


class ContextCommandResponse(BaseModel):
    """A single context command."""

    id: int | None = None
    name: str
    command_template: str
    description: str | None = None
    enabled: bool = True
    created_at: str | None = None


class ContextCommandListResponse(BaseModel):
    """List of context commands."""

    commands: list[ContextCommandResponse] = []


class ContextCommandCreateResponse(BaseModel):
    """Response after creating a context command."""

    id: int
    name: str
    message: str


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


# Rebuild QuoteEmbed to resolve the self-reference
QuoteEmbed.model_rebuild()
