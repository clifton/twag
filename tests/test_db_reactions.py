"""Tests for twag.db.reactions."""

from twag.db import get_connection, init_db
from twag.db.reactions import (
    delete_reaction,
    get_reactions_for_tweet,
    get_reactions_summary,
    insert_reaction,
)


def _setup_db(tmp_path):
    db_path = tmp_path / "test_reactions.db"
    init_db(db_path)
    return db_path


class TestInsertReaction:
    def test_returns_id(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            rid = insert_reaction(conn, "tweet_001", ">>", reason="Excellent analysis")
            assert rid > 0
            conn.commit()

    def test_multiple_reactions_different_ids(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            r1 = insert_reaction(conn, "tweet_001", ">>")
            r2 = insert_reaction(conn, "tweet_001", ">")
            assert r1 != r2
            conn.commit()


class TestGetReactionsForTweet:
    def test_filters_by_tweet_id(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            insert_reaction(conn, "tweet_001", ">>")
            insert_reaction(conn, "tweet_002", ">")
            conn.commit()

        with get_connection(db_path) as conn:
            reactions = get_reactions_for_tweet(conn, "tweet_001")
            assert len(reactions) == 1
            assert reactions[0].tweet_id == "tweet_001"
            assert reactions[0].reaction_type == ">>"

    def test_ordered_by_created_at_desc(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            r1 = insert_reaction(conn, "tweet_001", ">", reason="first")
            r2 = insert_reaction(conn, "tweet_001", ">>", reason="second")
            # Set explicit timestamps to guarantee ordering
            conn.execute(
                "UPDATE reactions SET created_at = '2025-01-01T10:00:00' WHERE id = ?", (r1,)
            )
            conn.execute(
                "UPDATE reactions SET created_at = '2025-01-01T12:00:00' WHERE id = ?", (r2,)
            )
            conn.commit()

        with get_connection(db_path) as conn:
            reactions = get_reactions_for_tweet(conn, "tweet_001")
            assert len(reactions) == 2
            # Most recent first
            assert reactions[0].reason == "second"

    def test_empty_result(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            reactions = get_reactions_for_tweet(conn, "nonexistent")
            assert reactions == []


class TestGetReactionsSummary:
    def test_counts_by_type(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            insert_reaction(conn, "t1", ">>")
            insert_reaction(conn, "t2", ">>")
            insert_reaction(conn, "t3", ">")
            insert_reaction(conn, "t4", "<")
            conn.commit()

        with get_connection(db_path) as conn:
            summary = get_reactions_summary(conn)
            assert summary[">>"] == 2
            assert summary[">"] == 1
            assert summary["<"] == 1

    def test_empty_db(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            summary = get_reactions_summary(conn)
            assert summary == {}


class TestDeleteReaction:
    def test_returns_true_if_found(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            rid = insert_reaction(conn, "tweet_001", ">>")
            conn.commit()

        with get_connection(db_path) as conn:
            assert delete_reaction(conn, rid) is True
            conn.commit()

        with get_connection(db_path) as conn:
            reactions = get_reactions_for_tweet(conn, "tweet_001")
            assert len(reactions) == 0

    def test_returns_false_if_not_found(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            assert delete_reaction(conn, 99999) is False
