"""Tests for twag.db.narratives."""

from datetime import datetime, timedelta, timezone

from twag.db import get_connection, init_db
from twag.db.narratives import (
    archive_stale_narratives,
    get_active_narratives,
    link_tweet_narrative,
    upsert_narrative,
)


def _setup_db(tmp_path):
    db_path = tmp_path / "test_narratives.db"
    init_db(db_path)
    # upsert_narrative uses ON CONFLICT(name) which requires a UNIQUE constraint
    with get_connection(db_path) as conn:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_narratives_name ON narratives(name)")
        conn.commit()
    return db_path


class TestUpsertNarrative:
    def test_insert_new(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            nid = upsert_narrative(conn, "AI regulation", sentiment="bearish", tickers=["GOOG"])
            assert nid > 0
            conn.commit()

    def test_update_increments_mention_count(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            upsert_narrative(conn, "Fed pivot")
            conn.commit()
        with get_connection(db_path) as conn:
            upsert_narrative(conn, "Fed pivot")
            conn.commit()
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT mention_count FROM narratives WHERE name = ?", ("Fed pivot",)).fetchone()
            assert row["mention_count"] == 2


class TestGetActiveNarratives:
    def test_returns_active_only(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            upsert_narrative(conn, "Active narrative")
            inactive_id = upsert_narrative(conn, "Inactive narrative")
            conn.execute("UPDATE narratives SET active = 0 WHERE id = ?", (inactive_id,))
            conn.commit()

        with get_connection(db_path) as conn:
            active = get_active_narratives(conn)
            names = [r["name"] for r in active]
            assert "Active narrative" in names
            assert "Inactive narrative" not in names

    def test_ordered_by_last_mentioned(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            upsert_narrative(conn, "Older")
            conn.execute(
                "UPDATE narratives SET last_mentioned_at = ? WHERE name = ?",
                ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat(), "Older"),
            )
            upsert_narrative(conn, "Newer")
            conn.commit()

        with get_connection(db_path) as conn:
            active = get_active_narratives(conn)
            assert active[0]["name"] == "Newer"


class TestLinkTweetNarrative:
    def test_insert_link(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            nid = upsert_narrative(conn, "Test narrative")
            # Need a tweet in the DB for FK, but tweet_narratives uses TEXT id
            # SQLite doesn't enforce FK by default, so we can test the insert
            link_tweet_narrative(conn, "tweet_001", nid)
            conn.commit()

            row = conn.execute(
                "SELECT * FROM tweet_narratives WHERE tweet_id = ? AND narrative_id = ?",
                ("tweet_001", nid),
            ).fetchone()
            assert row is not None

    def test_duplicate_is_noop(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            nid = upsert_narrative(conn, "Test narrative")
            link_tweet_narrative(conn, "tweet_001", nid)
            link_tweet_narrative(conn, "tweet_001", nid)  # No error
            conn.commit()

            count = conn.execute(
                "SELECT COUNT(*) FROM tweet_narratives WHERE tweet_id = ? AND narrative_id = ?",
                ("tweet_001", nid),
            ).fetchone()[0]
            assert count == 1


class TestArchiveStaleNarratives:
    def test_marks_old_as_inactive(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            upsert_narrative(conn, "Stale one")
            old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            conn.execute("UPDATE narratives SET last_mentioned_at = ? WHERE name = ?", (old_date, "Stale one"))
            conn.commit()

        with get_connection(db_path) as conn:
            archived = archive_stale_narratives(conn, days=7)
            conn.commit()
            assert archived >= 1

            row = conn.execute("SELECT active FROM narratives WHERE name = ?", ("Stale one",)).fetchone()
            assert row["active"] == 0

    def test_leaves_recent_active(self, tmp_path):
        db_path = _setup_db(tmp_path)
        with get_connection(db_path) as conn:
            upsert_narrative(conn, "Fresh one")
            conn.commit()

        with get_connection(db_path) as conn:
            archived = archive_stale_narratives(conn, days=7)
            conn.commit()
            assert archived == 0

            row = conn.execute("SELECT active FROM narratives WHERE name = ?", ("Fresh one",)).fetchone()
            assert row["active"] == 1
