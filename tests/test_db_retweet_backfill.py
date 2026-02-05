"""Tests for duplicate retweet metadata backfill during insert."""

from twag.db import get_connection, init_db, insert_tweet


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
