"""Bird CLI interaction: subprocess execution, rate limiting, and fetch commands."""

import json
import logging
import subprocess
import tempfile
import threading
import time
from typing import Any

from ..auth import get_auth_env
from ..config import load_config
from .extractors import Tweet, _extract_media_items_from_json_blob, _looks_truncated_text, _needs_retweet_hydration

log = logging.getLogger(__name__)

_BIRD_RATE_LOCK = threading.Lock()
_BIRD_LAST_CALL = 0.0
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
        with tempfile.TemporaryFile(mode="w+") as tmp:
            result = subprocess.run(
                cmd,
                stdout=tmp,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                env=env,
            )
            tmp.seek(0)
            stdout = tmp.read()
        if result.stderr.strip():
            lines = result.stderr.strip().splitlines()
            meaningful = [ln for ln in lines if not ln.strip().startswith("\u2139")]
            if meaningful:
                level = logging.WARNING if result.returncode == 0 else logging.ERROR
                log.log(level, "bird %s stderr: %s", args[0] if args else "?", "\n".join(meaningful))
        if result.returncode != 0:
            log.error("bird %s exited with code %d", args[0] if args else "?", result.returncode)
        return stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        log.error("bird %s timed out after %ds", args[0] if args else "?", timeout)
        return "", "Command timed out", 1
    except FileNotFoundError:
        log.error("bird CLI not found on PATH")
        return "", "bird CLI not found", 1


def _parse_bird_output(stdout: str) -> list[Tweet]:
    """Parse bird JSON output into Tweet objects.

    Handles three formats:
    1. A complete JSON array: ``[{...}, {...}]``
    2. NDJSON (one JSON object per line)
    3. A *truncated* JSON array (bird may clip stdout for large responses) —
       we recover every complete object before the truncation point.
    """
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
        text = stdout.strip()
        # Try NDJSON first (one JSON value per line)
        for line in text.split("\n"):
            line = line.strip()
            if not line:
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
        # If NDJSON found nothing and it looks like a truncated JSON array
        # (bird clips stdout at ~64 KB), recover complete objects via raw_decode.
        if not tweets and text.startswith("["):
            decoder = json.JSONDecoder()
            idx = 1  # skip opening '['
            while idx < len(text):
                while idx < len(text) and text[idx] in " \t\n\r,":
                    idx += 1
                if idx >= len(text) or text[idx] == "]":
                    break
                try:
                    obj, end = decoder.raw_decode(text, idx)
                    _append_item(obj)
                    idx = end
                except json.JSONDecodeError:
                    break
            if tweets:
                log.warning(
                    "bird output truncated at %d bytes; recovered %d tweets (some may be lost)",
                    len(stdout),
                    len(tweets),
                )

    return tweets


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


def fetch_home_timeline(count: int = 100) -> list[Tweet]:
    """Fetch home timeline tweets."""
    stdout, stderr, code = run_bird(["home", "-n", str(count), "--json"])

    if code != 0:
        raise RuntimeError(f"bird home failed (exit {code}): {stderr.strip()}")

    tweets = _parse_bird_output(stdout)
    if not tweets and stdout.strip():
        log.warning("bird home returned %d bytes but 0 parseable tweets", len(stdout))
    return _hydrate_truncated_retweets(tweets)


def fetch_user_tweets(handle: str, count: int = 50) -> list[Tweet]:
    """Fetch tweets from a specific user."""
    # Normalize handle
    if not handle.startswith("@"):
        handle = f"@{handle}"

    stdout, stderr, code = run_bird(["user-tweets", handle, "-n", str(count), "--json"])

    if code != 0:
        raise RuntimeError(f"bird user-tweets failed for {handle} (exit {code}): {stderr.strip()}")

    tweets = _parse_bird_output(stdout)
    return _hydrate_truncated_retweets(tweets)


def fetch_search(query: str, count: int = 30) -> list[Tweet]:
    """Search for tweets matching a query."""
    stdout, stderr, code = run_bird(["search", query, "-n", str(count), "--json"])

    if code != 0:
        raise RuntimeError(f"bird search failed (exit {code}): {stderr.strip()}")

    tweets = _parse_bird_output(stdout)
    return _hydrate_truncated_retweets(tweets)


def fetch_bookmarks(count: int = 100) -> list[Tweet]:
    """Fetch user's bookmarked tweets."""
    stdout, stderr, code = run_bird(["bookmarks", "-n", str(count), "--json"])

    if code != 0:
        raise RuntimeError(f"bird bookmarks failed (exit {code}): {stderr.strip()}")

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
    else:
        log.warning("bird read --json-full failed for %s (exit %d): %s", tweet_url_or_id, code, stderr.strip())

    stdout, stderr, code = run_bird(["read", tweet_url_or_id, "--json"])

    if code != 0:
        log.error("bird read failed for %s (exit %d): %s", tweet_url_or_id, code, stderr.strip())
        return None

    tweets = _parse_bird_output(stdout)
    if not tweets:
        log.warning("bird read returned output for %s but 0 parseable tweets", tweet_url_or_id)
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
