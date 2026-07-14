"""Regression tests for live search cache refreshes and cashtag queries."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from twag.db import get_connection, init_db, insert_tweet, search_tweets
from twag.search_live import LiveSearchError, _classify_with_timeout, refresh_search_cache


def test_cashtag_query_is_normalized_for_fts(tmp_path):
    """A shell-safe cashtag query should not crash SQLite FTS5."""
    db_path = tmp_path / "cashtag.db"
    init_db(db_path)
    with get_connection(db_path) as conn:
        insert_tweet(
            conn,
            tweet_id="blnd-1",
            author_handle="marketwatcher",
            content="Blend Labs $BLND announced a new partnership",
            created_at=datetime.now(timezone.utc),
            source="test",
        )
        conn.commit()

    with get_connection(db_path, readonly=True) as conn:
        results = search_tweets(conn, '$BLND OR "Blend Labs"')

    assert [result.id for result in results] == ["blnd-1"]


def test_live_refresh_filters_time_stores_and_classifies(monkeypatch):
    """Only in-window live results should enter the scoring pipeline."""
    import twag.search_live as live_mod

    now = datetime.now(timezone.utc)
    old = SimpleNamespace(id="old", created_at=now - timedelta(hours=2))
    recent = SimpleNamespace(id="recent", created_at=now - timedelta(minutes=5))
    stored = []
    classified = []

    def _fake_fetch(query, count, *, hydrate_retweets, timeout):
        assert hydrate_retweets is False
        assert timeout == 30
        return [old, recent]

    monkeypatch.setattr(live_mod, "fetch_search", _fake_fetch)

    def _fake_store(tweets, **kwargs):
        stored.extend(tweets)
        assert kwargs["source"] == "search"
        assert kwargs["quote_depth"] == 0
        return len(tweets), len(tweets)

    monkeypatch.setattr(live_mod, "store_fetched_tweets", _fake_store)
    monkeypatch.setattr(
        live_mod,
        "_classify_with_timeout",
        lambda ids, timeout: classified.append((ids, timeout)),
    )

    ids = refresh_search_cache(
        "NVIDIA",
        count=20,
        since=now - timedelta(hours=1),
        until=None,
        classify=True,
        classification_timeout=45,
    )

    assert ids == {"recent"}
    assert [tweet.id for tweet in stored] == ["recent"]
    assert classified == [({"recent"}, 45)]


def test_classification_timeout_terminates_worker(monkeypatch):
    """A stuck classification worker should be terminated at the overall deadline."""
    import twag.search_live as live_mod

    class _Process:
        returncode = None
        pid = 123

        def communicate(self, *, input, timeout):
            raise live_mod.subprocess.TimeoutExpired("worker", timeout)

    process = _Process()
    terminated = []
    monkeypatch.setattr(live_mod.subprocess, "Popen", lambda *args, **kwargs: process)

    def _record_termination(value):
        terminated.append(value)

    monkeypatch.setattr(live_mod, "_terminate_process", _record_termination)

    with pytest.raises(LiveSearchError, match="timed out after 12s"):
        _classify_with_timeout({"tweet-1"}, 12)

    assert terminated == [process]
