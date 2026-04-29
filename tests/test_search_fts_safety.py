"""Malformed FTS5 queries must not crash the search endpoint.

A user typing an unbalanced quote or a leading '*' in the search box
makes sqlite raise OperationalError. search_tweets retries with a
sanitized phrase and falls back to an empty list.
"""

from datetime import datetime, timezone

import pytest

from twag.db.connection import get_connection, init_db
from twag.db.search import sanitize_fts_query, search_tweets
from twag.db.tweets import insert_tweet


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("twag.db.connection.get_database_path", lambda: db_path)
    monkeypatch.setattr("twag.config.get_database_path", lambda: db_path)
    init_db(db_path)
    with get_connection(db_path) as conn:
        insert_tweet(
            conn,
            tweet_id="1",
            author_handle="alice",
            author_name="Alice",
            content="The Federal Reserve raised rates today.",
            created_at=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
        )
        conn.commit()
    return db_path


def test_sanitize_strips_fts5_punctuation():
    assert sanitize_fts_query('"unbalanced') == '"unbalanced"'
    assert sanitize_fts_query("foo*") == '"foo"'
    assert sanitize_fts_query("col:value") == '"col value"'
    assert sanitize_fts_query("(a OR b)") == '"a b"'


def test_sanitize_returns_empty_for_garbage():
    assert sanitize_fts_query("") == ""
    assert sanitize_fts_query("***") == ""
    assert sanitize_fts_query("AND OR NOT") == ""


def test_sanitize_strips_keywords():
    assert sanitize_fts_query("foo AND bar") == '"foo bar"'


def test_search_tweets_handles_malformed_quote(db):
    with get_connection(db) as conn:
        results = search_tweets(conn, '"unbalanced')
    # Either matches via sanitized retry or returns [] — must not raise.
    assert isinstance(results, list)


def test_search_tweets_handles_leading_star(db):
    with get_connection(db) as conn:
        results = search_tweets(conn, "*")
    assert isinstance(results, list)


def test_search_tweets_handles_unmatched_paren(db):
    with get_connection(db) as conn:
        results = search_tweets(conn, "(rates")
    assert isinstance(results, list)


def test_search_tweets_returns_empty_on_unrecoverable_error(db):
    """If both raw and sanitized queries fail, return [] rather than 500."""
    import sqlite3

    class FailingConn:
        def __init__(self, real):
            self._real = real

        def execute(self, *a, **kw):
            raise sqlite3.OperationalError("fts5: malformed")

        def __getattr__(self, name):
            return getattr(self._real, name)

    with get_connection(db) as conn:
        results = search_tweets(FailingConn(conn), '"foo')
    assert results == []


def test_search_tweets_still_works_for_valid_query(db):
    with get_connection(db) as conn:
        results = search_tweets(conn, "Federal")
    assert len(results) == 1
    assert results[0].author_handle == "alice"
