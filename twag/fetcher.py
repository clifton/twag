"""Bird CLI wrapper for fetching tweets."""

import html
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .config import load_config

_BIRD_RATE_LOCK = threading.Lock()
_BIRD_LAST_CALL = 0.0
_TRUNCATION_SUFFIXES = ("\u2026", "...")
_MAX_RETWEET_HYDRATIONS = 12


def _rate_limit_bird() -> None:
    config = load_config()
    min_interval = config.get("bird", {}).get("min_interval_seconds", 1.0)
    if not min_interval or min_interval <= 0:
        return

    global _BIRD_LAST_CALL
    with _BIRD_RATE_LOCK:
        now = time.monotonic()
        wait_for = min_interval - (now - _BIRD_LAST_CALL)
        if wait_for > 0:
            time.sleep(wait_for)
        _BIRD_LAST_CALL = time.monotonic()


@dataclass
class Tweet:
    """Parsed tweet data."""

    id: str
    author_handle: str
    author_name: str | None
    content: str
    created_at: datetime | None
    has_quote: bool
    quote_tweet_id: str | None
    has_media: bool
    media_items: list[dict[str, Any]]
    has_link: bool
    is_x_article: bool
    article_title: str | None
    article_preview: str | None
    article_text: str | None
    is_retweet: bool
    retweeted_by_handle: str | None
    retweeted_by_name: str | None
    original_tweet_id: str | None
    original_author_handle: str | None
    original_author_name: str | None
    original_content: str | None
    raw: dict[str, Any]

    @classmethod
    def from_bird_json(cls, data: dict[str, Any]) -> "Tweet":
        """Parse a tweet from bird CLI JSON output."""
        # Handle different field names bird might use
        tweet_id = _extract_tweet_id(data)

        # Author info
        author_handle, author_name = _extract_author(data)
        if not author_handle:
            author_handle = "unknown"

        # Content
        content = _extract_content(data)

        # Created at
        created_at = None
        created_str = data.get("createdAt") or data.get("created_at")
        if created_str:
            try:
                # Try ISO format first
                created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                try:
                    # Try Twitter's format
                    created_at = datetime.strptime(created_str, "%a %b %d %H:%M:%S %z %Y")
                except ValueError:
                    pass

        # Quote tweet
        has_quote = False
        quote_tweet_id = None
        if data.get("quotedTweet") or data.get("quoted_status"):
            has_quote = True
            quoted = data.get("quotedTweet") or data.get("quoted_status", {})
            quote_tweet_id = str(quoted.get("id") or quoted.get("id_str", ""))

        # Media
        media_items = _extract_media_items(data)
        is_x_article, article_title, article_preview, article_text = _extract_article(data)
        has_media = bool(
            media_items
            or data.get("media")
            or data.get("entities", {}).get("media")
            or data.get("extended_entities", {}).get("media")
        )

        # Links
        raw_legacy_urls = data.get("_raw", {}).get("legacy", {}).get("entities", {}).get("urls")
        has_link = bool(data.get("urls") or data.get("entities", {}).get("urls") or raw_legacy_urls)
        # Also check for links in text
        if not has_link:
            has_link = bool(re.search(r"https?://\S+", content))
        if is_x_article:
            has_link = True

        # Retweets
        is_retweet = False
        retweeted_by_handle = None
        retweeted_by_name = None
        original_tweet_id = None
        original_author_handle = None
        original_author_name = None
        original_content = None

        retweeted = _extract_retweeted_tweet(data)
        if retweeted:
            retweeted_handle, retweeted_name = _extract_author(retweeted)
            retweeted_content = _extract_content(retweeted)
            retweeted_id = _extract_tweet_id(retweeted)

            # Keep source author/content as-is for storage; expose original metadata separately.
            if retweeted_handle or retweeted_content or retweeted_id:
                is_retweet = True
                retweeted_by_handle = author_handle
                retweeted_by_name = author_name
                original_tweet_id = retweeted_id or None
                original_author_handle = retweeted_handle
                original_author_name = retweeted_name
                original_content = retweeted_content or None
        else:
            # Fallback for plain RT text when payload does not include retweeted metadata.
            # Example: "RT @original: text..."
            rt_match = re.match(r"^\s*RT\s+@([A-Za-z0-9_]{1,15}):\s*(.+)$", content or "")
            if rt_match:
                is_retweet = True
                retweeted_by_handle = author_handle
                retweeted_by_name = author_name
                original_author_handle = rt_match.group(1)
                fallback_original = rt_match.group(2).strip() or None
                if fallback_original and not _looks_truncated_text(fallback_original):
                    original_content = fallback_original

        return cls(
            id=tweet_id,
            author_handle=author_handle,
            author_name=author_name,
            content=content,
            created_at=created_at,
            has_quote=has_quote,
            quote_tweet_id=quote_tweet_id,
            has_media=has_media,
            media_items=media_items,
            has_link=has_link,
            is_x_article=is_x_article,
            article_title=article_title,
            article_preview=article_preview,
            article_text=article_text,
            is_retweet=is_retweet,
            retweeted_by_handle=retweeted_by_handle,
            retweeted_by_name=retweeted_by_name,
            original_tweet_id=original_tweet_id,
            original_author_handle=original_author_handle,
            original_author_name=original_author_name,
            original_content=original_content,
            raw=data,
        )


def _extract_tweet_id(data: dict[str, Any]) -> str:
    """Extract tweet ID from known bird/X payload variants."""
    return str(data.get("id") or data.get("id_str") or data.get("tweetId") or data.get("rest_id", ""))


def _extract_author(data: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extract author handle/name from known payload variants."""
    author = data.get("author", {}) or data.get("user", {})
    legacy = data.get("legacy", {}) if isinstance(data.get("legacy"), dict) else {}

    # GraphQL-style payloads sometimes nest under core.user_results.result
    core_result = (
        data.get("core", {}).get("user_results", {}).get("result", {}) if isinstance(data.get("core"), dict) else {}
    )
    core_legacy = core_result.get("legacy", {}) if isinstance(core_result, dict) else {}
    core_profile = core_result.get("core", {}) if isinstance(core_result, dict) else {}

    handle = (
        author.get("username")
        or author.get("screen_name")
        or author.get("handle")
        or legacy.get("screen_name")
        or core_legacy.get("screen_name")
        or core_profile.get("screen_name")
        or data.get("authorHandle")
    )

    name = (
        author.get("name")
        or author.get("display_name")
        or legacy.get("name")
        or core_legacy.get("name")
        or core_profile.get("name")
        or data.get("authorName")
    )

    return handle, name


def _extract_content(data: dict[str, Any]) -> str:
    """Extract tweet text from known payload variants."""
    legacy = data.get("legacy", {}) if isinstance(data.get("legacy"), dict) else {}
    note_candidates = []
    top_note_tweet = data.get("note_tweet", {}) if isinstance(data.get("note_tweet"), dict) else {}
    legacy_note_tweet = legacy.get("note_tweet", {}) if isinstance(legacy.get("note_tweet"), dict) else {}
    for note_tweet in (top_note_tweet, legacy_note_tweet):
        note_results = (
            note_tweet.get("note_tweet_results", {}).get("result", {})
            if isinstance(note_tweet.get("note_tweet_results"), dict)
            else {}
        )
        note_text = note_results.get("text")
        if isinstance(note_text, str) and note_text:
            note_candidates.append(note_text)

    base_text = (
        data.get("text")
        or data.get("full_text")
        or data.get("content")
        or legacy.get("full_text")
        or legacy.get("text")
        or ""
    )

    if note_candidates:
        longest_note = max(note_candidates, key=len)
        if len(longest_note) > len(base_text):
            return html.unescape(longest_note)

    return html.unescape(base_text)


def _extract_retweeted_tweet(data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract retweeted tweet payload from known variants."""
    retweeted = data.get("retweetedTweet") or data.get("retweeted_status") or data.get("retweetedStatus")
    if isinstance(retweeted, dict):
        return retweeted

    retweeted_result = data.get("retweeted_status_result")
    if isinstance(retweeted_result, dict):
        result = retweeted_result.get("result")
        if isinstance(result, dict):
            return result

    # Bird --json-full commonly nests retweeted metadata here.
    nested_result = (
        data.get("_raw", {}).get("legacy", {}).get("retweeted_status_result", {}).get("result")
        if isinstance(data.get("_raw"), dict)
        else None
    )
    if isinstance(nested_result, dict):
        return nested_result

    return None


def _looks_truncated_text(text: str | None) -> bool:
    if not text:
        return False
    stripped = text.rstrip()
    return bool(stripped) and stripped.endswith(_TRUNCATION_SUFFIXES)


def _needs_retweet_hydration(tweet: Tweet) -> bool:
    if not tweet.is_retweet:
        return False
    if tweet.original_tweet_id and tweet.original_content and not _looks_truncated_text(tweet.original_content):
        return False
    if tweet.original_content and _looks_truncated_text(tweet.original_content):
        return True
    return _looks_truncated_text(tweet.content)


def _hydrate_truncated_retweets(tweets: list[Tweet]) -> list[Tweet]:
    reads = 0
    for tweet in tweets:
        if reads >= _MAX_RETWEET_HYDRATIONS:
            break
        if not _needs_retweet_hydration(tweet):
            continue

        hydrated = read_tweet(tweet.id)
        reads += 1
        if not hydrated or not hydrated.is_retweet:
            continue
        if not hydrated.original_content or _looks_truncated_text(hydrated.original_content):
            continue

        tweet.is_retweet = True
        tweet.retweeted_by_handle = hydrated.retweeted_by_handle or tweet.retweeted_by_handle or tweet.author_handle
        tweet.retweeted_by_name = hydrated.retweeted_by_name or tweet.retweeted_by_name or tweet.author_name
        tweet.original_tweet_id = hydrated.original_tweet_id or tweet.original_tweet_id
        tweet.original_author_handle = hydrated.original_author_handle or tweet.original_author_handle
        tweet.original_author_name = hydrated.original_author_name or tweet.original_author_name
        tweet.original_content = hydrated.original_content

    return tweets


def _extract_article(data: dict[str, Any]) -> tuple[bool, str | None, str | None, str | None]:
    """Extract X native article payload fields from bird JSON."""
    top_article = data.get("article") if isinstance(data.get("article"), dict) else {}
    raw_article = (
        data.get("_raw", {}).get("article", {}).get("article_results", {}).get("result", {})
        if isinstance(data.get("_raw"), dict)
        else {}
    )

    if not top_article and not raw_article:
        return False, None, None, None

    title = top_article.get("title") or raw_article.get("title") or None
    preview = top_article.get("previewText") or raw_article.get("preview_text") or None
    text = raw_article.get("plain_text")
    if not text:
        text = _extract_article_text_from_blocks(raw_article)
    if not text:
        # bird --json often returns the full article body in tweet text while omitting
        # _raw.article.plain_text. Use it when it is clearly richer than preview.
        content = _extract_content(data).strip()
        preview = (top_article.get("previewText") or raw_article.get("preview_text") or "").strip()
        if content and (len(content) >= 400 or (preview and len(content) >= len(preview) + 80)):
            text = content

    return True, title, preview, text


def _extract_article_text_from_blocks(article_result: dict[str, Any]) -> str | None:
    """Fallback article text extraction from content_state blocks."""
    content_state = article_result.get("content_state") if isinstance(article_result, dict) else {}
    blocks = content_state.get("blocks") if isinstance(content_state, dict) else None
    if not isinstance(blocks, list):
        return None

    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if not isinstance(text, str):
            continue
        stripped = text.strip()
        if stripped:
            parts.append(stripped)

    if not parts:
        return None
    return "\n".join(parts)


def _extract_media_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def _extend(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    candidates.append(item)

    _extend(data.get("extended_entities", {}).get("media"))
    _extend(data.get("entities", {}).get("media"))
    _extend(data.get("media"))

    # Some variants nest media under a dict
    media_dict = data.get("media")
    if isinstance(media_dict, dict):
        _extend(media_dict.get("items"))

    # X article media entities and cover image can hold chart/document visuals.
    raw_article_result = (
        data.get("_raw", {}).get("article", {}).get("article_results", {}).get("result", {})
        if isinstance(data.get("_raw"), dict)
        else {}
    )
    raw_media_entities = raw_article_result.get("media_entities")
    if isinstance(raw_media_entities, list):
        for media in raw_media_entities:
            if not isinstance(media, dict):
                continue
            media_info = media.get("media_info") if isinstance(media.get("media_info"), dict) else {}
            url = media_info.get("original_img_url")
            if not url:
                continue
            candidates.append(
                {
                    "url": url,
                    "type": "photo",
                    "source": "article",
                    "media_id": media.get("media_id"),
                }
            )

    cover_media = raw_article_result.get("cover_media") if isinstance(raw_article_result, dict) else {}
    if isinstance(cover_media, dict):
        cover_info = cover_media.get("media_info") if isinstance(cover_media.get("media_info"), dict) else {}
        cover_url = cover_info.get("original_img_url")
        if cover_url:
            candidates.append(
                {
                    "url": cover_url,
                    "type": "photo",
                    "source": "article_cover",
                    "media_id": cover_media.get("media_id"),
                }
            )

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in candidates:
        url = item.get("media_url_https") or item.get("media_url") or item.get("url")
        if not url:
            variants = item.get("video_info", {}).get("variants", [])
            if variants:
                url = variants[0].get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        item_data: dict[str, Any] = {
            "url": url,
            "type": item.get("type") or item.get("media_type") or "photo",
        }
        if item.get("source"):
            item_data["source"] = item["source"]
        if item.get("media_id"):
            item_data["media_id"] = item["media_id"]
        items.append(item_data)

    return items


def _extract_media_items_from_json_blob(blob: str) -> list[dict[str, Any]]:
    """Best-effort media extraction from potentially truncated bird --json-full output."""
    if not blob:
        return []

    urls: list[str] = []
    patterns = [
        r'"original_img_url"\s*:\s*"([^"]+)"',
        r'"media_url_https"\s*:\s*"([^"]+)"',
        r'"media_url"\s*:\s*"([^"]+)"',
    ]
    for pattern in patterns:
        urls.extend(re.findall(pattern, blob))

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_url in urls:
        url = raw_url.replace("\\/", "/")
        if not url.startswith("http"):
            continue
        if url in seen:
            continue
        seen.add(url)
        items.append({"url": url, "type": "photo", "source": "article_full_fallback"})
    return items


def get_auth_env() -> dict[str, str]:
    """Get authentication environment variables."""
    # Load from ~/.env if it exists
    env_file = os.path.expanduser("~/.env")
    env = os.environ.copy()

    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    # Handle 'export KEY=value' format
                    if line.startswith("export "):
                        line = line[7:]
                    key, value = line.split("=", 1)
                    # Remove quotes if present
                    value = value.strip("\"'")
                    env[key] = value

    return env


def run_bird(args: list[str], timeout: int = 60) -> tuple[str, str, int]:
    """Run bird CLI command, returning (stdout, stderr, returncode)."""
    _rate_limit_bird()
    env = get_auth_env()

    # Build command with auth if available
    cmd = ["bird", *args]

    # Add auth flags if we have the tokens
    auth_token = env.get("AUTH_TOKEN")
    ct0 = env.get("CT0")

    if auth_token and "--auth-token" not in args:
        cmd.extend(["--auth-token", auth_token])
    if ct0 and "--ct0" not in args:
        cmd.extend(["--ct0", ct0])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1
    except FileNotFoundError:
        return "", "bird CLI not found", 1


def _parse_bird_output(stdout: str) -> list[Tweet]:
    """Parse bird JSON output into Tweet objects."""
    if not stdout.strip():
        return []

    tweets: list[Tweet] = []

    def _append_item(item: Any) -> None:
        if isinstance(item, dict):
            tweets.append(Tweet.from_bird_json(item))

    try:
        data = json.loads(stdout)
        if isinstance(data, list):
            for item in data:
                _append_item(item)
        else:
            _append_item(data)
    except json.JSONDecodeError:
        # Fallback: try line-by-line for NDJSON format
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if isinstance(item, list):
                    for i in item:
                        _append_item(i)
                else:
                    _append_item(item)
            except json.JSONDecodeError:
                continue

    return tweets


def fetch_home_timeline(count: int = 100) -> list[Tweet]:
    """Fetch home timeline tweets."""
    stdout, stderr, code = run_bird(["home", "-n", str(count), "--json"])

    if code != 0:
        raise RuntimeError(f"bird home failed: {stderr}")

    tweets = _parse_bird_output(stdout)
    return _hydrate_truncated_retweets(tweets)


def fetch_user_tweets(handle: str, count: int = 50) -> list[Tweet]:
    """Fetch tweets from a specific user."""
    # Normalize handle
    if not handle.startswith("@"):
        handle = f"@{handle}"

    stdout, stderr, code = run_bird(["user-tweets", handle, "-n", str(count), "--json"])

    if code != 0:
        raise RuntimeError(f"bird user-tweets failed for {handle}: {stderr}")

    tweets = _parse_bird_output(stdout)
    return _hydrate_truncated_retweets(tweets)


def fetch_search(query: str, count: int = 30) -> list[Tweet]:
    """Search for tweets matching a query."""
    stdout, stderr, code = run_bird(["search", query, "-n", str(count), "--json"])

    if code != 0:
        raise RuntimeError(f"bird search failed: {stderr}")

    tweets = _parse_bird_output(stdout)
    return _hydrate_truncated_retweets(tweets)


def fetch_bookmarks(count: int = 100) -> list[Tweet]:
    """Fetch user's bookmarked tweets."""
    stdout, stderr, code = run_bird(["bookmarks", "-n", str(count), "--json"])

    if code != 0:
        raise RuntimeError(f"bird bookmarks failed: {stderr}")

    tweets = _parse_bird_output(stdout)
    return _hydrate_truncated_retweets(tweets)


def read_tweet(tweet_url_or_id: str) -> Tweet | None:
    """Read a single tweet by URL or ID."""
    # Prefer --json-full for richer article payloads (body/media). Some long payloads
    # can be truncated by bird; in that case fall back to --json and merge media hints.
    stdout, stderr, code = run_bird(["read", tweet_url_or_id, "--json-full"])
    recovered_media: list[dict[str, Any]] = []
    if code == 0:
        tweets = _parse_bird_output(stdout)
        if tweets:
            return tweets[0]
        recovered_media = _extract_media_items_from_json_blob(stdout)

    stdout, stderr, code = run_bird(["read", tweet_url_or_id, "--json"])

    if code != 0:
        return None

    tweets = _parse_bird_output(stdout)
    if not tweets:
        return None

    tweet = tweets[0]
    if recovered_media:
        existing_urls = {item.get("url") for item in tweet.media_items}
        for item in recovered_media:
            if item["url"] not in existing_urls:
                tweet.media_items.append(item)
        tweet.has_media = bool(tweet.media_items)

    return tweet


def get_tweet_url(tweet_id: str, author_handle: str = "i") -> str:
    """Construct a tweet URL."""
    handle = author_handle.lstrip("@")
    return f"https://x.com/{handle}/status/{tweet_id}"
