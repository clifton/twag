"""Tests for schema version tracking and migration system."""

import sqlite3

import pytest

from twag.db import get_connection, get_schema_version, init_db, upsert_narrative
from twag.db.schema import LATEST_SCHEMA_VERSION


@pytest.fixture
def fresh_db(tmp_path):
    """Create a fresh database via init_db."""
    path = tmp_path / "fresh.db"
    init_db(path)
    return path


class TestFreshDatabase:
    """Tests for fresh database initialization."""

    def test_schema_version_table_exists(self, fresh_db):
        with get_connection(fresh_db) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
            assert cursor.fetchone() is not None

    def test_schema_version_is_latest(self, fresh_db):
        with get_connection(fresh_db) as conn:
            version = get_schema_version(conn)
        assert version == LATEST_SCHEMA_VERSION

    def test_idx_tweets_reply_exists(self, fresh_db):
        with get_connection(fresh_db) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tweets_reply'")
            assert cursor.fetchone() is not None

    def test_narratives_name_unique(self, fresh_db):
        with get_connection(fresh_db) as conn:
            conn.execute("INSERT INTO narratives (name, sentiment) VALUES ('test_narrative', 'bullish')")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO narratives (name, sentiment) VALUES ('test_narrative', 'bearish')")


class TestLegacyMigration:
    """Tests for migrating a pre-versioned database."""

    def _create_legacy_db(self, path):
        """Create a minimal legacy database without schema_version."""
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tweets (
                id TEXT PRIMARY KEY,
                author_handle TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP,
                first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source TEXT,
                processed_at TIMESTAMP,
                relevance_score REAL,
                category TEXT,
                summary TEXT,
                signal_tier TEXT,
                tickers TEXT,
                has_quote INTEGER DEFAULT 0,
                quote_tweet_id TEXT,
                has_media INTEGER DEFAULT 0,
                media_analysis TEXT,
                has_link INTEGER DEFAULT 0,
                link_summary TEXT,
                included_in_digest TEXT,
                FOREIGN KEY (quote_tweet_id) REFERENCES tweets(id)
            );
            CREATE TABLE IF NOT EXISTS accounts (
                handle TEXT PRIMARY KEY,
                display_name TEXT,
                tier INTEGER DEFAULT 2,
                weight REAL DEFAULT 50.0,
                category TEXT,
                tweets_seen INTEGER DEFAULT 0,
                tweets_kept INTEGER DEFAULT 0,
                avg_relevance_score REAL,
                last_high_signal_at TIMESTAMP,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                auto_promoted INTEGER DEFAULT 0,
                muted INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS narratives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_mentioned_at TIMESTAMP,
                mention_count INTEGER DEFAULT 1,
                sentiment TEXT,
                related_tickers TEXT,
                active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS tweet_narratives (
                tweet_id TEXT,
                narrative_id INTEGER,
                PRIMARY KEY (tweet_id, narrative_id)
            );
            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tweets_fetched INTEGER,
                new_tweets INTEGER,
                query_params TEXT
            );
            CREATE TABLE IF NOT EXISTS reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tweet_id TEXT NOT NULL,
                reaction_type TEXT NOT NULL,
                reason TEXT,
                target TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tweet_id) REFERENCES tweets(id)
            );
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                template TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by TEXT
            );
            CREATE TABLE IF NOT EXISTS prompt_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_name TEXT NOT NULL,
                template TEXT NOT NULL,
                version INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS context_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                command_template TEXT NOT NULL,
                description TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_tweets_created ON tweets(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tweets_score ON tweets(relevance_score DESC);
        """)
        conn.commit()
        conn.close()

    def test_legacy_db_gets_migrated_to_latest(self, tmp_path):
        path = tmp_path / "legacy.db"
        self._create_legacy_db(path)

        # Run init_db which should detect legacy and migrate
        init_db(path)

        with get_connection(path) as conn:
            version = get_schema_version(conn)
            assert version == LATEST_SCHEMA_VERSION

    def test_legacy_db_gets_missing_columns(self, tmp_path):
        path = tmp_path / "legacy.db"
        self._create_legacy_db(path)
        init_db(path)

        with get_connection(path) as conn:
            cursor = conn.execute("PRAGMA table_info(tweets)")
            columns = {row[1] for row in cursor.fetchall()}

        assert "bookmarked" in columns
        assert "is_retweet" in columns
        assert "is_x_article" in columns
        assert "links_json" in columns
        assert "in_reply_to_tweet_id" in columns

    def test_legacy_db_gets_narratives_unique_index(self, tmp_path):
        path = tmp_path / "legacy.db"
        self._create_legacy_db(path)
        init_db(path)

        with get_connection(path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_narratives_name'")
            assert cursor.fetchone() is not None

    def test_legacy_db_gets_reply_index(self, tmp_path):
        path = tmp_path / "legacy.db"
        self._create_legacy_db(path)
        init_db(path)

        with get_connection(path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tweets_reply'")
            assert cursor.fetchone() is not None


class TestUpsertNarrativeUniqueness:
    """Test that upsert_narrative correctly updates on conflict."""

    def test_upsert_updates_existing(self, fresh_db):
        with get_connection(fresh_db) as conn:
            id1 = upsert_narrative(conn, "inflation", sentiment="bearish")
            id2 = upsert_narrative(conn, "inflation", sentiment="bullish")
            assert id1 == id2

            row = conn.execute("SELECT mention_count FROM narratives WHERE id = ?", (id1,)).fetchone()
            assert row[0] == 2

    def test_different_narratives_get_different_ids(self, fresh_db):
        with get_connection(fresh_db) as conn:
            id1 = upsert_narrative(conn, "inflation")
            id2 = upsert_narrative(conn, "deflation")
            assert id1 != id2
