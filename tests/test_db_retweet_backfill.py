"""Tests for duplicate retweet metadata backfill during insert."""

import json
import sqlite3

import twag.db.connection as db_connection_mod
from twag.db import get_connection, get_tweet_by_id, init_db, insert_tweet


def test_insert_tweet_duplicate_backfills_retweet_metadata(tmp_path):
    db_path = tmp_path / "twag_backfill.db"
    init_db(db_path)

    with get_connection(db_path) as conn:
        inserted = insert_tweet(
            conn,
            tweet_id="rt-1",
            author_handle="retweeter",
            content="RT @orig: truncated payload…",
            source="test",
        )
        assert inserted is True

        inserted = insert_tweet(
            conn,
            tweet_id="rt-1",
            author_handle="retweeter",
            content="RT @orig: truncated payload…",
            source="test",
            is_retweet=True,
            retweeted_by_handle="retweeter",
            retweeted_by_name="Retweeter Name",
            original_tweet_id="orig-1",
            original_author_handle="orig",
            original_author_name="Original Name",
            original_content="Full original text recovered from read API.",
        )
        assert inserted is False
        conn.commit()

        row = conn.execute(
            """
            SELECT
                is_retweet,
                retweeted_by_handle,
                original_tweet_id,
                original_author_handle,
                original_author_name,
                original_content
            FROM tweets
            WHERE id = 'rt-1'
            """
        ).fetchone()

    assert row is not None
    assert row["is_retweet"] == 1
    assert row["retweeted_by_handle"] == "retweeter"
    assert row["original_tweet_id"] == "orig-1"
    assert row["original_author_handle"] == "orig"
    assert row["original_author_name"] == "Original Name"
    assert row["original_content"] == "Full original text recovered from read API."


def test_insert_tweet_duplicate_does_not_overwrite_good_original_content_with_truncated(tmp_path):
    db_path = tmp_path / "twag_backfill_no_regress.db"
    init_db(db_path)

    with get_connection(db_path) as conn:
        inserted = insert_tweet(
            conn,
            tweet_id="rt-2",
            author_handle="retweeter",
            content="RT @orig: full text",
            source="test",
            is_retweet=True,
            original_content="Recovered full text that should be preserved.",
        )
        assert inserted is True

        inserted = insert_tweet(
            conn,
            tweet_id="rt-2",
            author_handle="retweeter",
            content="RT @orig: truncated payload…",
            source="test",
            is_retweet=True,
            original_content="clipped fallback…",
        )
        assert inserted is False
        conn.commit()

        row = conn.execute("SELECT original_content FROM tweets WHERE id = 'rt-2'").fetchone()

    assert row is not None
    assert row["original_content"] == "Recovered full text that should be preserved."


def test_insert_tweet_duplicate_replaces_short_prefix_with_longer_original_content(tmp_path):
    db_path = tmp_path / "twag_backfill_longer.db"
    init_db(db_path)

    with get_connection(db_path) as conn:
        inserted = insert_tweet(
            conn,
            tweet_id="rt-3",
            author_handle="retweeter",
            content="RT @orig: partial payload",
            source="test",
            is_retweet=True,
            original_content="for me the odds that AI is a bubble declined significantly in the last 3 weeks",
        )
        assert inserted is True

        longer = (
            "for me the odds that AI is a bubble declined significantly in the last 3 weeks and the odds "
            "that we're actually quite under-built for the necessary levels of inference/usage went significantly up "
            "in that period and parallel agents will be deployed in knowledge work"
        )
        inserted = insert_tweet(
            conn,
            tweet_id="rt-3",
            author_handle="retweeter",
            content="RT @orig: partial payload",
            source="test",
            is_retweet=True,
            original_content=longer,
        )
        assert inserted is False
        conn.commit()

        row = conn.execute("SELECT original_content FROM tweets WHERE id = 'rt-3'").fetchone()

    assert row is not None
    assert row["original_content"] == longer


def test_insert_tweet_sanitizes_malformed_unicode_across_text_and_json_fields(tmp_path):
    db_path = tmp_path / "twag_unicode_sanitize.db"
    init_db(db_path)

    with get_connection(db_path) as conn:
        inserted = insert_tweet(
            conn,
            tweet_id="tweet-\ud83d",
            author_handle="author\ud83d",
            author_name="Author \udc49",
            content="Broken \ud83d[\udc49 content",
            source="dep\ud83d",
            has_media=True,
            media_items=[{"url": "https://example.com/\ud83d.png", "type": "photo\udc49"}],
            has_link=True,
            links=[
                {"url": "https://t.co/\ud83d", "expanded_url": "https://example.com/\udc49", "display_url": "bad\ud83d"}
            ],
            is_x_article=True,
            article_title="Title \ud83d",
            article_preview="Preview \udc49",
            article_text="Article \ud83d[\udc49 text",
            is_retweet=True,
            retweeted_by_handle="rt\ud83d",
            retweeted_by_name="Retweeter \udc49",
            original_tweet_id="orig\ud83d",
            original_author_handle="orig_author\udc49",
            original_author_name="Original \ud83d",
            original_content="Original \ud83d[\udc49 text",
        )
        assert inserted is True
        conn.commit()

        row = get_tweet_by_id(conn, "tweet-\ufffd")

    assert row is not None
    assert row["author_handle"] == "author\ufffd"
    assert row["author_name"] == "Author \ufffd"
    assert row["content"] == "Broken \ufffd[\ufffd content"
    assert row["source"] == "dep\ufffd"
    assert row["article_title"] == "Title \ufffd"
    assert row["article_preview"] == "Preview \ufffd"
    assert row["article_text"] == "Article \ufffd[\ufffd text"
    assert row["retweeted_by_handle"] == "rt\ufffd"
    assert row["retweeted_by_name"] == "Retweeter \ufffd"
    assert row["original_tweet_id"] == "orig\ufffd"
    assert row["original_author_handle"] == "orig_author\ufffd"
    assert row["original_author_name"] == "Original \ufffd"
    assert row["original_content"] == "Original \ufffd[\ufffd text"

    media_items = json.loads(row["media_items"])
    assert media_items == [{"url": "https://example.com/\ufffd.png", "type": "photo\ufffd"}]

    links = json.loads(row["links_json"])
    assert links == [
        {
            "url": "https://t.co/\ufffd",
            "expanded_url": "https://example.com/\ufffd",
            "display_url": "bad\ufffd",
        }
    ]


def test_insert_tweet_retries_transient_database_lock(monkeypatch):
    class _LockOnceConnection:
        def __init__(self):
            self.calls = 0
            self.params = None

        def execute(self, _sql, params):
            self.calls += 1
            if self.calls == 1:
                raise sqlite3.OperationalError("database is locked")
            self.params = params

    conn = _LockOnceConnection()
    sleeps: list[float] = []
    monkeypatch.setattr(db_connection_mod.time, "sleep", lambda delay: sleeps.append(delay))

    inserted = insert_tweet(
        conn,
        tweet_id="retry-1",
        author_handle="retry_user",
        content="retry content",
        source="test",
    )

    assert inserted is True
    assert conn.calls == 2
    assert sleeps == [2.0]
    assert conn.params is not None
