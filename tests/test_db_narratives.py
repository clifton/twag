"""Tests for twag.db.narratives — narrative CRUD with in-memory SQLite."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from twag.db.narratives import (
    archive_stale_narratives,
    get_active_narratives,
    link_tweet_narrative,
    upsert_narrative,
)


@pytest.fixture
def conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE narratives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_mentioned_at TIMESTAMP,
            mention_count INTEGER DEFAULT 1,
            sentiment TEXT,
            related_tickers TEXT,
            active INTEGER DEFAULT 1
        );
        CREATE TABLE tweet_narratives (
            tweet_id TEXT,
            narrative_id INTEGER,
            PRIMARY KEY (tweet_id, narrative_id)
        );
        """,
    )
    return conn


class TestUpsertNarrative:
    def test_insert_returns_new_id(self, conn: sqlite3.Connection) -> None:
        nid = upsert_narrative(conn, "Fed pivot", sentiment="bullish", tickers=["TLT", "GLD"])
        assert nid > 0
        row = conn.execute("SELECT * FROM narratives WHERE id=?", (nid,)).fetchone()
        assert row["name"] == "Fed pivot"
        assert row["sentiment"] == "bullish"
        assert json.loads(row["related_tickers"]) == ["TLT", "GLD"]
        assert row["mention_count"] == 1

    def test_insert_with_no_tickers_stores_null(self, conn: sqlite3.Connection) -> None:
        upsert_narrative(conn, "Soft landing")
        row = conn.execute("SELECT related_tickers FROM narratives WHERE name='Soft landing'").fetchone()
        assert row["related_tickers"] is None

    def test_repeat_increments_mention_count(self, conn: sqlite3.Connection) -> None:
        nid_1 = upsert_narrative(conn, "AI bubble", sentiment="bearish")
        nid_2 = upsert_narrative(conn, "AI bubble")
        assert nid_1 == nid_2
        row = conn.execute("SELECT mention_count, sentiment FROM narratives WHERE id=?", (nid_1,)).fetchone()
        assert row["mention_count"] == 2
        # Sentiment is preserved when the new value is None (COALESCE).
        assert row["sentiment"] == "bearish"

    def test_repeat_can_overwrite_sentiment(self, conn: sqlite3.Connection) -> None:
        upsert_narrative(conn, "Recession", sentiment="bearish")
        upsert_narrative(conn, "Recession", sentiment="neutral")
        row = conn.execute("SELECT sentiment FROM narratives WHERE name='Recession'").fetchone()
        assert row["sentiment"] == "neutral"


class TestGetActiveNarratives:
    def test_only_returns_active_rows(self, conn: sqlite3.Connection) -> None:
        upsert_narrative(conn, "Active one")
        upsert_narrative(conn, "Inactive one")
        conn.execute("UPDATE narratives SET active=0 WHERE name='Inactive one'")
        rows = get_active_narratives(conn)
        names = [r["name"] for r in rows]
        assert "Active one" in names
        assert "Inactive one" not in names

    def test_orders_by_last_mentioned_desc(self, conn: sqlite3.Connection) -> None:
        upsert_narrative(conn, "Older")
        upsert_narrative(conn, "Newer")
        # Force older timestamp on the first row.
        old_ts = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        conn.execute("UPDATE narratives SET last_mentioned_at=? WHERE name='Older'", (old_ts,))
        rows = get_active_narratives(conn)
        assert rows[0]["name"] == "Newer"


class TestLinkTweetNarrative:
    def test_link_creates_row(self, conn: sqlite3.Connection) -> None:
        nid = upsert_narrative(conn, "Theme")
        link_tweet_narrative(conn, "tweet-1", nid)
        row = conn.execute("SELECT * FROM tweet_narratives").fetchone()
        assert row["tweet_id"] == "tweet-1"
        assert row["narrative_id"] == nid

    def test_duplicate_link_silently_ignored(self, conn: sqlite3.Connection) -> None:
        nid = upsert_narrative(conn, "Theme")
        link_tweet_narrative(conn, "tweet-1", nid)
        # Second call must not raise.
        link_tweet_narrative(conn, "tweet-1", nid)
        rows = conn.execute("SELECT COUNT(*) AS n FROM tweet_narratives").fetchone()
        assert rows["n"] == 1


class TestArchiveStaleNarratives:
    def test_marks_stale_and_returns_count(self, conn: sqlite3.Connection) -> None:
        upsert_narrative(conn, "Fresh")
        upsert_narrative(conn, "Stale")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        conn.execute("UPDATE narratives SET last_mentioned_at=? WHERE name='Stale'", (stale_ts,))

        count = archive_stale_narratives(conn, days=7)
        assert count == 1
        stale = conn.execute("SELECT active FROM narratives WHERE name='Stale'").fetchone()
        fresh = conn.execute("SELECT active FROM narratives WHERE name='Fresh'").fetchone()
        assert stale["active"] == 0
        assert fresh["active"] == 1

    def test_already_inactive_rows_not_re_archived(self, conn: sqlite3.Connection) -> None:
        upsert_narrative(conn, "Was inactive")
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        conn.execute(
            "UPDATE narratives SET active=0, last_mentioned_at=? WHERE name='Was inactive'",
            (stale_ts,),
        )
        # WHERE active = 1 filter excludes already-inactive rows.
        assert archive_stale_narratives(conn, days=7) == 0
