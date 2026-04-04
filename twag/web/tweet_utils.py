"""Shared tweet content utilities."""

import html
from datetime import datetime
from typing import Any

from ..link_utils import (
    LinkNormalizationResult,
    normalize_tweet_links,
)


def parse_created_at(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_links_for_display(
    *,
    tweet_id: str,
    text: str | None,
    links: list[dict] | None,
    has_media: bool = False,
) -> LinkNormalizationResult:
    return normalize_tweet_links(
        tweet_id=tweet_id,
        text=text,
        links=links,
        has_media=has_media,
        already_expanded=True,
    )


def decode_html_entities(text: str | None) -> str | None:
    if text is None:
        return None
    return html.unescape(text)


def quote_embed_from_row(row) -> dict[str, Any]:
    created_at = parse_created_at(row["created_at"])
    return {
        "id": row["id"],
        "author_handle": row["author_handle"],
        "author_name": row["author_name"],
        "content": decode_html_entities(row["content"]),
        "created_at": created_at.isoformat() if created_at else None,
    }
