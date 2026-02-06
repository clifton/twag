"""Shared tweet content utilities."""

import html
import re
from datetime import datetime
from typing import Any

from ..link_utils import (
    LinkNormalizationResult,
    normalize_tweet_links,
    parse_tweet_status_id,
    remove_urls_from_text,
)

_TWEET_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:mobile\.)?(?:x|twitter)\.com/(?:i/(?:web/)?|[^/]+/)?status/(\d+)(?:\?[^\s]+)?",
    re.IGNORECASE,
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


def extract_tweet_links(text: str) -> list[tuple[str, str]]:
    return [(match.group(1), match.group(0)) for match in _TWEET_URL_RE.finditer(text)]


def remove_tweet_links(text: str, links: list[tuple[str, str]], remove_ids: set[str]) -> str:
    cleaned = text
    urls_to_remove: set[str] = set()
    for tweet_id, url in links:
        if tweet_id not in remove_ids:
            continue
        urls_to_remove.add(url)
    cleaned = remove_urls_from_text(cleaned, urls_to_remove)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


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


def parse_tweet_id_from_url(url: str | None) -> str | None:
    return parse_tweet_status_id(url)


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
