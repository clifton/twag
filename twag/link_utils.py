"""Utilities for extracting and classifying links in tweet text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_TRAILING_PUNCT_RE = re.compile(r"[)\],.?!:;]+$")
_STATUS_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:mobile\.)?(?:x|twitter)\.com/(?:i/(?:web/)?|[^/]+/)?status/(\d+)(?:\?[^\s]+)?",
    re.IGNORECASE,
)


@dataclass
class LinkNormalizationResult:
    display_text: str
    inline_tweet_links: list[dict[str, str]]
    external_links: list[dict[str, str]]


def clean_url_candidate(url: str) -> str:
    """Trim punctuation commonly attached to URLs in plain text."""
    cleaned = url.strip()
    cleaned = _TRAILING_PUNCT_RE.sub("", cleaned)
    return cleaned


def parse_tweet_status_id(url: str | None) -> str | None:
    """Extract status id from a twitter/x status URL."""
    if not url:
        return None
    match = _STATUS_URL_RE.search(url)
    if not match:
        return None
    return match.group(1)


def extract_urls_from_text(text: str | None) -> list[str]:
    """Extract plain URLs from text."""
    if not text:
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.finditer(text):
        url = clean_url_candidate(match.group(0))
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _domain_for(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except ValueError:
        return ""


def _normalize_structured_links(text: str, links: list[dict]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()

    for item in links:
        if not isinstance(item, dict):
            continue
        raw_url = clean_url_candidate(str(item.get("url") or ""))
        expanded_url = clean_url_candidate(str(item.get("expanded_url") or item.get("expandedUrl") or ""))
        display_url = str(item.get("display_url") or item.get("displayUrl") or "").strip()
        resolved = expanded_url or raw_url
        if not resolved:
            continue
        key = (raw_url, resolved)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        normalized.append(
            {
                "url": raw_url or resolved,
                "expanded_url": resolved,
                "display_url": display_url,
            }
        )

    known_urls = {item["url"] for item in normalized} | {item["expanded_url"] for item in normalized}
    for raw in extract_urls_from_text(text):
        if raw in known_urls:
            continue
        normalized.append({"url": raw, "expanded_url": raw, "display_url": ""})

    return normalized


def remove_urls_from_text(text: str, urls_to_remove: set[str]) -> str:
    """Remove URL tokens from text while preserving the rest of the content."""
    if not text or not urls_to_remove:
        return text

    lines: list[str] = []
    for line in text.splitlines():
        updated = line
        for url in sorted(urls_to_remove, key=len, reverse=True):
            if not url:
                continue
            updated = re.sub(rf"(^|\s){re.escape(url)}(?=\s|$)", " ", updated)
        updated = re.sub(r"\s{2,}", " ", updated).strip()
        if updated:
            lines.append(updated)

    return "\n".join(lines).strip()


def normalize_tweet_links(
    *,
    tweet_id: str,
    text: str | None,
    links: list[dict] | None,
) -> LinkNormalizationResult:
    """
    Normalize links for display and embedding rules.

    Rules:
    - Self tweet links are removed from display text.
    - Twitter/x status links to other tweets are treated as inline tweet embeds.
    - Non-status links are returned as external links.
    """
    raw_text = text or ""
    normalized_links = _normalize_structured_links(raw_text, links or [])

    urls_to_remove: set[str] = set()
    inline_tweet_links: list[dict[str, str]] = []
    external_links: list[dict[str, str]] = []

    seen_inline_ids: set[str] = set()
    seen_external_urls: set[str] = set()

    for link in normalized_links:
        raw_url = link["url"]
        expanded_url = link["expanded_url"]
        display_url = link["display_url"]
        status_id = parse_tweet_status_id(expanded_url) or parse_tweet_status_id(raw_url)
        if status_id:
            urls_to_remove.add(raw_url)
            urls_to_remove.add(expanded_url)
            if status_id == tweet_id or status_id in seen_inline_ids:
                continue
            seen_inline_ids.add(status_id)
            inline_tweet_links.append(
                {
                    "id": status_id,
                    "url": expanded_url or raw_url,
                }
            )
            continue

        resolved = expanded_url or raw_url
        if not resolved or resolved in seen_external_urls:
            continue
        urls_to_remove.add(raw_url)
        urls_to_remove.add(expanded_url)
        seen_external_urls.add(resolved)
        external_links.append(
            {
                "url": resolved,
                "display_url": display_url or resolved,
                "domain": _domain_for(resolved),
            }
        )

    display_text = remove_urls_from_text(raw_text, urls_to_remove)
    return LinkNormalizationResult(
        display_text=display_text,
        inline_tweet_links=inline_tweet_links,
        external_links=external_links,
    )
