"""Tests for twag.db.reactions — reaction CRUD with in-memory SQLite."""

from datetime import datetime, timezone

from twag.db import get_connection, init_db, insert_tweet
from twag.db.reactions import (
    delete_reaction,
    get_reactions_for_tweet,
    get_reactions_summary,
    insert_reaction,
)


def _setup_db_with_tweet(tmp_path, tweet_id="tweet-1"):
    db_path = tmp_path / "test_reactions.db"
    init_db(db_path)
    with get_connection(db_path) as conn:
        insert_tweet(
            conn,
            tweet_id=tweet_id,
            author_handle="test_user",
            content="Test tweet content",
            created_at=datetime.now(timezone.utc),
            source="test",
        )
        conn.commit()
    return db_path


def test_insert_and_get_reaction(tmp_path):
    db_path = _setup_db_with_tweet(tmp_path)
    with get_connection(db_path) as conn:
        rid = insert_reaction(conn, "tweet-1", ">>", reason="Great signal")
        conn.commit()
        assert rid > 0
        reactions = get_reactions_for_tweet(conn, "tweet-1")
        assert len(reactions) == 1
        assert reactions[0].reaction_type == ">>"
        assert reactions[0].reason == "Great signal"
        assert reactions[0].tweet_id == "tweet-1"


def test_get_reactions_for_tweet_empty(tmp_path):
    db_path = _setup_db_with_tweet(tmp_path)
    with get_connection(db_path) as conn:
        reactions = get_reactions_for_tweet(conn, "tweet-1")
        assert reactions == []


def test_get_reactions_summary(tmp_path):
    db_path = _setup_db_with_tweet(tmp_path)
    with get_connection(db_path) as conn:
        insert_reaction(conn, "tweet-1", ">>")
        insert_reaction(conn, "tweet-1", ">")
        insert_reaction(conn, "tweet-1", ">>")
        conn.commit()
        summary = get_reactions_summary(conn)
        assert summary[">>"] == 2
        assert summary[">"] == 1


def test_get_reactions_summary_empty(tmp_path):
    db_path = _setup_db_with_tweet(tmp_path)
    with get_connection(db_path) as conn:
        summary = get_reactions_summary(conn)
        assert summary == {}


def test_delete_reaction(tmp_path):
    db_path = _setup_db_with_tweet(tmp_path)
    with get_connection(db_path) as conn:
        rid = insert_reaction(conn, "tweet-1", "<")
        conn.commit()
        assert delete_reaction(conn, rid) is True
        conn.commit()
        assert get_reactions_for_tweet(conn, "tweet-1") == []


def test_delete_reaction_nonexistent(tmp_path):
    db_path = _setup_db_with_tweet(tmp_path)
    with get_connection(db_path) as conn:
        assert delete_reaction(conn, 9999) is False


def test_insert_reaction_with_target(tmp_path):
    db_path = _setup_db_with_tweet(tmp_path)
    with get_connection(db_path) as conn:
        insert_reaction(conn, "tweet-1", "x_author", target="spammer")
        conn.commit()
        reactions = get_reactions_for_tweet(conn, "tweet-1")
        assert reactions[0].target == "spammer"
