"""Bird CLI interaction: subprocess execution, rate limiting, and fetch commands."""

import json
import logging
import os
import random
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Any

from ..auth import get_auth_env
from ..config import load_config
from ..taxonomy import Metric
from .extractors import Tweet, _looks_truncated_text, _needs_retweet_hydration

log = logging.getLogger(__name__)

_BIRD_RATE_LOCK = threading.Lock()
_BIRD_LAST_CALL = 0.0
_MAX_RETWEET_HYDRATIONS = 12

_SENSITIVE_ENV_VARS = ("AUTH_TOKEN", "CT0", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN")
_HEX_PATTERN = re.compile(r"[0-9a-fA-F]{32,}")


def _redact_stderr(stderr: str) -> str:
    """Strip credential values and long hex strings from bird stderr before logging."""
    redacted = stderr
    for var in _SENSITIVE_ENV_VARS:
        value = os.environ.get(var)
        if value and value in redacted:
            redacted = redacted.replace(value, f"<{var}>")
    redacted = _HEX_PATTERN.sub("<redacted-hex>", redacted)
    return redacted


@dataclass(frozen=True)
class ReadTweetFailure:
    """Classified failure for ``bird read``."""

    reason: str
    retryable: bool
    auth_related: bool = False


@dataclass(frozen=True)
class ReadTweetResult:
    """Detailed result for ``bird read``."""

    tweet: Tweet | None
    failure: ReadTweetFailure | None = None


def _is_rate_limited(stderr: str) -> bool:
    """Check if bird CLI stderr indicates a 429 rate limit."""
    return "429" in stderr or "Rate limit" in stderr or "rate limit" in stderr


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


def _run_bird_once(
    cmd: list[str],
    env: dict[str, str],
    args: list[str],
    timeout: int,
    *,
    log_failures: bool = True,
) -> tuple[str, str, int]:
    """Execute a single bird CLI subprocess call."""
    try:
        with tempfile.TemporaryFile(mode="w+") as tmp:
            result = subprocess.run(
                cmd,
                stdout=tmp,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                env=env,
                check=False,
            )
            tmp.seek(0)
            stdout = tmp.read()
        if result.stderr.strip():
            lines = result.stderr.strip().splitlines()
            meaningful = [ln for ln in lines if not ln.strip().startswith("\u2139")]
            if meaningful and log_failures:
                level = logging.WARNING if result.returncode == 0 else logging.ERROR
                log.log(level, "bird %s stderr: %s", args[0] if args else "?", _redact_stderr("\n".join(meaningful)))
        if result.returncode != 0 and log_failures:
            log.error("bird %s exited with code %d", args[0] if args else "?", result.returncode)
        return stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        log.error("bird %s timed out after %ds", args[0] if args else "?", timeout)  # noqa: TRY400
        return "", "Command timed out", 1
    except FileNotFoundError:
        log.error("bird CLI not found on PATH")  # noqa: TRY400
        return "", "bird CLI not found", 1


def run_bird(args: list[str], timeout: int = 60, *, log_failures: bool = True) -> tuple[str, str, int]:
    """Run bird CLI command with retry on rate limit, returning (stdout, stderr, returncode)."""
    from twag.metrics import get_collector

    m = get_collector()
    m.inc(Metric.FETCHER_CALLS)
    t0 = time.monotonic()
    _rate_limit_bird()
    env = get_auth_env()

    # Build command with auth if available
    cmd = ["bird", *args]

    # Auth tokens are passed as CLI flags because bird (v0.8.0) does not support
    # reading AUTH_TOKEN/CT0 from environment variables.  This means tokens are
    # visible in /proc/<pid>/cmdline.  Accepted trade-off for a single-user local
    # tool — revisit if bird adds env-var auth support.
    auth_token = env.get("AUTH_TOKEN")
    ct0 = env.get("CT0")

    if auth_token and "--auth-token" not in args:
        cmd.extend(["--auth-token", auth_token])
    if ct0 and "--ct0" not in args:
        cmd.extend(["--ct0", ct0])

    config = load_config()
    bird_cfg = config.get("bird", {})
    max_attempts = bird_cfg.get("retry_max_attempts", 4)
    base_seconds = bird_cfg.get("retry_base_seconds", 15.0)
    max_seconds = bird_cfg.get("retry_max_seconds", 120.0)

    for attempt in range(max_attempts):
        stdout, stderr, returncode = _run_bird_once(cmd, env, args, timeout, log_failures=log_failures)

        if returncode == 0 or not _is_rate_limited(stderr):
            m.observe(Metric.FETCHER_LATENCY, time.monotonic() - t0)
            if returncode != 0:
                m.inc(Metric.FETCHER_ERRORS)
            return stdout, stderr, returncode

        if attempt + 1 >= max_attempts:
            log.error("bird %s rate-limited after %d attempts, giving up", args[0] if args else "?", max_attempts)
            m.observe(Metric.FETCHER_LATENCY, time.monotonic() - t0)
            m.inc(Metric.FETCHER_ERRORS)
            return stdout, stderr, returncode

        m.inc(Metric.FETCHER_RETRIES)
        delay = min(base_seconds * (2**attempt), max_seconds)
        jitter = random.uniform(0, delay * 0.25)
        wait = delay + jitter
        log.warning(
            "bird %s rate-limited (attempt %d/%d), retrying in %.0fs",
            args[0] if args else "?",
            attempt + 1,
            max_attempts,
            wait,
        )
        time.sleep(wait)
        _rate_limit_bird()

    m.observe(Metric.FETCHER_LATENCY, time.monotonic() - t0)
    return stdout, stderr, returncode


def _is_auth_failure(stderr: str) -> bool:
    lower = stderr.lower()
    return any(
        token in lower
        for token in (
            "auth",
            "unauthorized",
            "forbidden",
            "login",
            "cookie",
            "ct0",
            "auth_token",
            "csrf",
            "403",
        )
    )


def _is_retryable_read_failure(stderr: str) -> bool:
    lower = stderr.lower()
    return _is_rate_limited(stderr) or any(
        token in lower
        for token in (
            "timed out",
            "timeout",
            "temporary",
            "temporarily",
            "try again",
            "connection reset",
            "connection refused",
            "connection aborted",
            "network",
            "unavailable",
            "internal server error",
            "bad gateway",
            "gateway timeout",
            "service unavailable",
            "502",
            "503",
            "504",
        )
    )


def _summarize_read_failure(stderr: str, *, code: int) -> ReadTweetFailure:
    message = stderr.strip() or f"bird read failed with exit code {code}"
    normalized = " ".join(message.split())

    if _is_auth_failure(message):
        return ReadTweetFailure(
            reason=f"authentication/authorization failure: {normalized}",
            retryable=True,
            auth_related=True,
        )
    if _is_retryable_read_failure(message):
        return ReadTweetFailure(reason=f"transient bird/X failure: {normalized}", retryable=True)
    if "not found" in message.lower():
        return ReadTweetFailure(reason=f"tweet unavailable or missing: {normalized}", retryable=False)
    return ReadTweetFailure(reason=f"non-retryable bird read failure: {normalized}", retryable=False)


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
        for raw_line in text.split("\n"):
            line = raw_line.strip()
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


def read_tweet_with_diagnostics(tweet_url_or_id: str) -> ReadTweetResult:
    """Read a single tweet by URL or ID with failure classification."""
    stdout, stderr, code = run_bird(["read", tweet_url_or_id, "--json-full"], log_failures=False)

    if code != 0:
        return ReadTweetResult(tweet=None, failure=_summarize_read_failure(stderr, code=code))

    tweets = _parse_bird_output(stdout)
    if not tweets:
        if stdout.strip():
            reason = "bird returned output but no parseable tweet payload"
        else:
            reason = "bird returned no tweet payload"
        return ReadTweetResult(tweet=None, failure=ReadTweetFailure(reason=reason, retryable=False))

    return ReadTweetResult(tweet=tweets[0])


def read_tweet(tweet_url_or_id: str) -> Tweet | None:
    """Read a single tweet by URL or ID."""
    result = read_tweet_with_diagnostics(tweet_url_or_id)
    if result.failure:
        log.warning("bird read skipped %s: %s", tweet_url_or_id, result.failure.reason)
        return None
    return result.tweet


def get_tweet_url(tweet_id: str, author_handle: str = "i") -> str:
    """Construct a tweet URL."""
    handle = author_handle.lstrip("@")
    return f"https://x.com/{handle}/status/{tweet_id}"
