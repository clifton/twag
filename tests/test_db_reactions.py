"""Tests for twag.db.reactions."""

import sqlite3

import pytest

from twag.db.reactions import (
    delete_reaction,
    get_reactions_for_tweet,
    get_reactions_summary,
    get_reactions_with_tweets,
    insert_reaction,
)
from twag.db.schema import SCHEMA


@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    yield conn
    conn.close()


def _insert_tweet(db, tweet_id="t1", author="alice", content="hello"):
    db.execute(
        "INSERT INTO tweets (id, author_handle, content) VALUES (?, ?, ?)",
        (tweet_id, author, content),
    )
    db.commit()


class TestInsertReaction:
    def test_insert_returns_id(self, db):
        _insert_tweet(db)
        rid = insert_reaction(db, "t1", ">>", reason="great call")
        db.commit()
        assert rid > 0

    def test_insert_with_target(self, db):
        _insert_tweet(db)
        rid = insert_reaction(db, "t1", "x_author", target="spammer")
        db.commit()
        row = db.execute("SELECT * FROM reactions WHERE id = ?", (rid,)).fetchone()
        assert row["target"] == "spammer"


class TestGetReactionsForTweet:
    def test_returns_reactions(self, db):
        _insert_tweet(db)
        insert_reaction(db, "t1", ">>")
        insert_reaction(db, "t1", ">")
        db.commit()
        results = get_reactions_for_tweet(db, "t1")
        assert len(results) == 2
        types = {r.reaction_type for r in results}
        assert types == {">>", ">"}

    def test_empty_for_unknown_tweet(self, db):
        results = get_reactions_for_tweet(db, "nonexistent")
        assert results == []


class TestGetReactionsSummary:
    def test_counts_by_type(self, db):
        _insert_tweet(db)
        insert_reaction(db, "t1", ">>")
        insert_reaction(db, "t1", ">>")
        insert_reaction(db, "t1", "<")
        db.commit()
        summary = get_reactions_summary(db)
        assert summary[">>"] == 2
        assert summary["<"] == 1

    def test_empty_db(self, db):
        summary = get_reactions_summary(db)
        assert summary == {}


class TestDeleteReaction:
    def test_delete_existing(self, db):
        _insert_tweet(db)
        rid = insert_reaction(db, "t1", ">>")
        db.commit()
        assert delete_reaction(db, rid) is True

    def test_delete_nonexistent(self, db):
        assert delete_reaction(db, 999) is False


class TestGetReactionsWithTweets:
    def test_join_with_tweet_data(self, db):
        _insert_tweet(db, "t1", "alice", "test tweet")
        insert_reaction(db, "t1", ">>", reason="good")
        db.commit()
        results = get_reactions_with_tweets(db)
        assert len(results) == 1
        reaction, row = results[0]
        assert reaction.reaction_type == ">>"
        assert row["author_handle"] == "alice"

    def test_filter_by_type(self, db):
        _insert_tweet(db)
        insert_reaction(db, "t1", ">>")
        insert_reaction(db, "t1", "<")
        db.commit()
        results = get_reactions_with_tweets(db, reaction_type=">>")
        assert len(results) == 1
        assert results[0][0].reaction_type == ">>"

    def test_missing_tweet_excluded(self, db):
        # Insert reaction for a tweet that doesn't exist — JOIN excludes it
        db.execute(
            "INSERT INTO reactions (tweet_id, reaction_type) VALUES (?, ?)",
            ("missing", ">>"),
        )
        db.commit()
        results = get_reactions_with_tweets(db)
        assert len(results) == 0
