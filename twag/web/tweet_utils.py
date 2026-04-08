"""Shared tweet content utilities."""

import html
import re as _re
from datetime import datetime
from typing import Any

from ..link_utils import (
    LinkNormalizationResult,
    normalize_tweet_links,
)


def parse_created_at(value: str | datetime | None) -> datetime | None:
    """Parse a created_at value into a datetime, accepting ISO strings or passthrough."""
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
    """Normalize a tweet's links for web/digest display, assuming URLs are already expanded."""
    return normalize_tweet_links(
        tweet_id=tweet_id,
        text=text,
        links=links,
        has_media=has_media,
        already_expanded=True,
    )


def decode_html_entities(text: str | None) -> str | None:
    """Decode HTML entities (e.g. &amp;) in text, returning None for None input."""
    if text is None:
        return None
    return html.unescape(text)


def quote_embed_from_row(row) -> dict[str, Any]:
    """Build a quote-embed dict from a database row for API/display rendering."""
    created_at = parse_created_at(row["created_at"])
    return {
        "id": row["id"],
        "author_handle": row["author_handle"],
        "author_name": row["author_name"],
        "content": decode_html_entities(row["content"]),
        "created_at": created_at.isoformat() if created_at else None,
    }


# Backward-compatibility shims (removed in v0.2, will be deleted in v0.3)
_TWEET_URL_RE = _re.compile(
    r"https?://(?:www\.)?(?:mobile\.)?(?:x|twitter)\.com/(?:i/(?:web/)?|[^/]+/)?status/(\d+)(?:\?[^\s]+)?",
    _re.IGNORECASE,
)


def extract_tweet_links(text: str) -> list[tuple[str, str]]:
    """Deprecated: use twag.link_utils functions directly."""
    from twag._compat import _deprecated

    _deprecated(
        "twag.web.tweet_utils.extract_tweet_links",
        "twag.link_utils.normalize_tweet_links",
    )
    return [(m.group(1), m.group(0)) for m in _TWEET_URL_RE.finditer(text)]


def remove_tweet_links(
    text: str,
    links: list[tuple[str, str]],
    remove_ids: set[str],
) -> str:
    """Deprecated: use twag.link_utils.remove_urls_from_text directly."""
    from twag._compat import _deprecated

    from ..link_utils import remove_urls_from_text

    _deprecated(
        "twag.web.tweet_utils.remove_tweet_links",
        "twag.link_utils.remove_urls_from_text",
    )
    urls_to_remove: set[str] = set()
    for tweet_id, url in links:
        if tweet_id in remove_ids:
            urls_to_remove.add(url)
    cleaned = remove_urls_from_text(text, urls_to_remove)
    cleaned = _re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def parse_tweet_id_from_url(url: str | None) -> str | None:
    """Deprecated: use twag.link_utils.parse_tweet_status_id directly."""
    from twag._compat import _deprecated

    from ..link_utils import parse_tweet_status_id

    _deprecated(
        "twag.web.tweet_utils.parse_tweet_id_from_url",
        "twag.link_utils.parse_tweet_status_id",
    )
    return parse_tweet_status_id(url)
