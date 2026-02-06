"""Utilities for extracting and classifying links in tweet text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from urllib.parse import urlparse
from urllib.request import Request, urlopen

_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_TRAILING_PUNCT_RE = re.compile(r"[)\],.?!:;]+$")
_STATUS_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:mobile\.)?(?:x|twitter)\.com/(?:i/(?:web/)?|[^/]+/)?status/(\d+)(?:\?[^\s]+)?",
    re.IGNORECASE,
)
_SHORTENER_DOMAINS = {"t.co"}
_MAX_SHORT_URL_EXPANSIONS = 2
_SHORT_URL_HEAD_TIMEOUT_SECONDS = 1.0
_SHORT_URL_GET_TIMEOUT_SECONDS = 1.5
# Guardrail for worst-case API request latency when entities are missing and we
# need network-based t.co expansion. Kept high enough to avoid degrading
# quality across normal sessions.
_MAX_NETWORK_EXPANSION_ATTEMPTS = 512
_network_expansion_attempts = 0
_network_expansion_lock = Lock()


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


def _display_url_for(url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    query = f"?{parsed.query}" if parsed.query else ""
    if not host:
        return url
    return f"{host}{path}{query}"


def _is_shortener_url(url: str) -> bool:
    return _domain_for(url).split(":")[0] in _SHORTENER_DOMAINS


@lru_cache(maxsize=1024)
def _expand_short_url(url: str) -> str:
    """Resolve short URLs (e.g., t.co) to their final destination."""
    cleaned = clean_url_candidate(url)
    if not cleaned or not _is_shortener_url(cleaned):
        return cleaned
    global _network_expansion_attempts
    with _network_expansion_lock:
        if _network_expansion_attempts >= _MAX_NETWORK_EXPANSION_ATTEMPTS:
            return cleaned
        _network_expansion_attempts += 1
    headers = {"User-Agent": "twag/1.0 (+https://github.com/clifton/twag)"}
    attempts = (
        ("HEAD", _SHORT_URL_HEAD_TIMEOUT_SECONDS),
        ("GET", _SHORT_URL_GET_TIMEOUT_SECONDS),
    )
    for method, timeout in attempts:
        try:
            request = Request(cleaned, method=method, headers=headers)
            with urlopen(request, timeout=timeout) as response:
                resolved = clean_url_candidate(response.geturl() or cleaned)
                if resolved:
                    return resolved
        except Exception:
            continue
    return cleaned


def _normalize_structured_links(text: str, links: list[dict]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()
    short_url_expansions = 0

    for item in links:
        if not isinstance(item, dict):
            continue
        raw_url = clean_url_candidate(str(item.get("url") or ""))
        expanded_url = clean_url_candidate(str(item.get("expanded_url") or item.get("expandedUrl") or ""))
        display_url = str(item.get("display_url") or item.get("displayUrl") or "").strip()
        resolved = expanded_url or raw_url
        if resolved and _is_shortener_url(resolved) and short_url_expansions < _MAX_SHORT_URL_EXPANSIONS:
            resolved = _expand_short_url(resolved)
            short_url_expansions += 1
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
                "display_url": display_url or _display_url_for(resolved),
            }
        )

    known_urls = {item["url"] for item in normalized} | {item["expanded_url"] for item in normalized}
    for raw in extract_urls_from_text(text):
        if raw in known_urls:
            continue
        resolved = raw
        if _is_shortener_url(raw) and short_url_expansions < _MAX_SHORT_URL_EXPANSIONS:
            resolved = _expand_short_url(raw)
            short_url_expansions += 1
        normalized.append({"url": raw, "expanded_url": resolved, "display_url": _display_url_for(resolved)})

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


def replace_urls_in_text(text: str, replacements: dict[str, str]) -> str:
    """Replace URL tokens in text with supplied replacements."""
    if not text or not replacements:
        return text

    lines: list[str] = []
    for line in text.splitlines():
        updated = line
        for source in sorted(replacements, key=len, reverse=True):
            replacement = replacements[source]
            if not source or not replacement:
                continue
            updated = re.sub(rf"(^|\s){re.escape(source)}(?=\s|$)", rf"\1{replacement}", updated)
        updated = re.sub(r"\s{2,}", " ", updated).strip()
        if updated:
            lines.append(updated)

    return "\n".join(lines).strip()


def normalize_tweet_links(
    *,
    tweet_id: str,
    text: str | None,
    links: list[dict] | None,
    has_media: bool = False,
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
    external_replacements: dict[str, str] = {}
    inline_tweet_links: list[dict[str, str]] = []
    external_links: list[dict[str, str]] = []

    seen_inline_ids: set[str] = set()
    seen_external_urls: set[str] = set()
    unresolved_short_links: list[tuple[str, str]] = []

    for link in normalized_links:
        raw_url = link["url"]
        expanded_url = link["expanded_url"]
        resolved = expanded_url or raw_url
        if resolved and _is_shortener_url(resolved):
            unresolved_short_links.append((raw_url, expanded_url))

    # Trailing unresolved t.co links are often self/media pointers that should
    # not render in digests/UI. For non-media tweets, apply this only when at
    # least one link in the post already resolved to a non-short URL.
    has_resolved_non_short = any(
        bool(
            (item.get("expanded_url") or item.get("url"))
            and not _is_shortener_url(item.get("expanded_url") or item.get("url"))
        )
        for item in normalized_links
    )
    should_prune_trailing_unresolved = has_media or has_resolved_non_short
    if should_prune_trailing_unresolved and unresolved_short_links:
        unresolved_values = {value for pair in unresolved_short_links for value in pair if value}
        ordered_urls = extract_urls_from_text(raw_text)
        trailing = ordered_urls[-1] if ordered_urls else ""
        if trailing and trailing in unresolved_values:
            for short_raw, short_expanded in unresolved_short_links:
                if trailing in (short_raw, short_expanded):
                    urls_to_remove.add(short_raw)
                    urls_to_remove.add(short_expanded)

    for link in normalized_links:
        raw_url = link["url"]
        expanded_url = link["expanded_url"]
        display_url = link["display_url"]
        if raw_url in urls_to_remove or expanded_url in urls_to_remove:
            continue
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
        if raw_url and raw_url != resolved:
            external_replacements[raw_url] = resolved
        seen_external_urls.add(resolved)
        external_links.append(
            {
                "url": resolved,
                "display_url": display_url or _display_url_for(resolved),
                "domain": _domain_for(resolved),
            }
        )

    display_text = replace_urls_in_text(raw_text, external_replacements)
    display_text = remove_urls_from_text(display_text, urls_to_remove)
    return LinkNormalizationResult(
        display_text=display_text,
        inline_tweet_links=inline_tweet_links,
        external_links=external_links,
    )
