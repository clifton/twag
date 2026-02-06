"""Pydantic models for tweet link normalization."""

from __future__ import annotations

from pydantic import BaseModel


class TweetLink(BaseModel):
    """A raw link extracted from a tweet."""

    url: str
    expanded_url: str = ""
    display_url: str = ""


class InlineTweetLink(BaseModel):
    """A link to another tweet found inline in text."""

    id: str
    url: str = ""


class ExternalLink(BaseModel):
    """An external (non-tweet) link."""

    url: str
    display_url: str = ""
    domain: str = ""


class LinkNormalizationResult(BaseModel):
    """Result of normalizing tweet links for display."""

    display_text: str = ""
    inline_tweet_links: list[dict[str, str]] = []
    external_links: list[dict[str, str]] = []
