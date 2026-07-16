"""Live X search fallback for cache misses."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone

from .fetcher import fetch_search
from .processor import store_fetched_tweets

_BIRD_LIVE_SEARCH_TIMEOUT_SECONDS = 30


class LiveSearchError(RuntimeError):
    """A safe, user-facing live search failure."""


def _as_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime for reliable range comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _tweet_is_in_range(tweet, since: datetime | None, until: datetime | None) -> bool:
    """Check a fetched tweet against optional half-open UTC bounds."""
    if since is None and until is None:
        return True
    if tweet.created_at is None:
        return False

    created_at = _as_utc(tweet.created_at)
    if since is not None and created_at < _as_utc(since):
        return False
    return until is None or created_at < _as_utc(until)


def refresh_search_cache(
    query: str,
    *,
    count: int,
    since: datetime | None,
    until: datetime | None,
    classify: bool,
    classification_timeout: int,
) -> set[str]:
    """Fetch a live X query, persist in-range tweets, and optionally classify them.

    Returns the IDs of fetched tweets inside the requested time range. Error
    messages deliberately omit backend stderr so cookie values cannot leak.
    """
    try:
        tweets = fetch_search(
            query=query,
            count=count,
            hydrate_retweets=False,
            timeout=_BIRD_LIVE_SEARCH_TIMEOUT_SECONDS,
        )
    except RuntimeError as exc:
        raise LiveSearchError(
            "live bird search failed within 30s; verify X authentication with `bird whoami`",
        ) from exc

    in_range = [tweet for tweet in tweets if _tweet_is_in_range(tweet, since, until)]
    if not in_range:
        return set()

    try:
        store_fetched_tweets(
            in_range,
            source="search",
            query_params={"query": query, "count": count, "live_fallback": True},
            quote_depth=0,
        )
    except Exception as exc:
        raise LiveSearchError("live search results could not be stored") from exc

    if not classify:
        return {tweet.id for tweet in in_range if tweet.id}

    tweet_ids = {tweet.id for tweet in in_range if tweet.id}
    _classify_with_timeout(tweet_ids, classification_timeout)

    return tweet_ids


def _classify_with_timeout(tweet_ids: set[str], timeout: int) -> None:
    """Run triage-only classification in a killable, bounded child process."""
    if not tweet_ids:
        return

    process = subprocess.Popen(
        [sys.executable, "-m", "twag.search_classify_worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=os.name == "posix",
    )
    try:
        process.communicate(input=json.dumps(sorted(tweet_ids)), timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_process(process)
        raise LiveSearchError(f"live result classification timed out after {timeout}s") from exc

    if process.returncode != 0:
        raise LiveSearchError("live result classification failed")


def _terminate_process(process: subprocess.Popen) -> None:
    """Terminate a timed-out worker and escalate if it does not exit."""
    if process.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()
