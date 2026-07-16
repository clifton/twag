"""Guarded additive migration coverage for P0 signal fields."""

import sqlite3
from datetime import datetime, timezone

from twag.db import SCHEMA, get_connection, get_tweet_stats, init_db, insert_tweet

SIGNAL_COLUMNS = {
    "surprise",
    "is_stale_repeat",
    "themes",
    "playbook_trigger",
    "catalyst_status",
    "direction",
    "story_key",
    "signal_emitted_at",
}


def test_legacy_database_gets_additive_signal_columns_idempotently(tmp_path):
    db_path = tmp_path / "legacy.db"
    legacy_schema = SCHEMA
    for definition in (
        "    surprise INTEGER,\n",
        "    is_stale_repeat INTEGER,\n",
        "    themes TEXT,\n",
        "    playbook_trigger TEXT,\n",
        "    catalyst_status TEXT,\n",
        "    direction TEXT,\n",
        "    story_key TEXT,\n",
        "    signal_emitted_at TEXT,\n",
    ):
        legacy_schema = legacy_schema.replace(definition, "")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(legacy_schema)

    init_db(db_path)
    init_db(db_path)
    with get_connection(db_path, readonly=True) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tweets)")}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(tweets)")}
    assert columns >= SIGNAL_COLUMNS
    assert "idx_tweets_story_key" in indexes


def test_stats_date_uses_eastern_calendar_bounds(tmp_path):
    db_path = tmp_path / "stats.db"
    init_db(db_path)
    with get_connection(db_path) as conn:
        insert_tweet(conn, "late-et", "a", "x", created_at=datetime(2026, 7, 17, 3, 30, tzinfo=timezone.utc))
        insert_tweet(conn, "next-et", "a", "x", created_at=datetime(2026, 7, 17, 4, 30, tzinfo=timezone.utc))
        conn.commit()
        stats = get_tweet_stats(conn, date="2026-07-16")
    assert stats["total"] == 1
