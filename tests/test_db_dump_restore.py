"""Tests for database dump and restore with FTS5 compatibility."""

import gzip
import sqlite3

import pytest

from twag.db import (
    _is_fts_statement,
    dump_sql,
    get_connection,
    init_db,
    insert_tweet,
    restore_sql,
    search_tweets,
    upsert_account,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database with schema and sample data."""
    path = tmp_path / "test.db"
    init_db(path)

    with get_connection(path) as conn:
        # Insert sample tweets
        for i in range(5):
            insert_tweet(
                conn,
                tweet_id=f"tweet_{i}",
                author_handle=f"user_{i}",
                content=f"Test tweet content about inflation and markets #{i}",
                source="test",
            )
        # Insert sample accounts
        for i in range(3):
            upsert_account(conn, f"user_{i}", tier=1)
        conn.commit()

    return path


class TestIsFilteredStatement:
    """Tests for _is_fts_statement helper."""

    def test_pragma_writable_schema(self):
        assert _is_fts_statement("PRAGMA writable_schema=ON;")
        assert _is_fts_statement("PRAGMA writable_schema=OFF;")

    def test_insert_sqlite_master(self):
        assert _is_fts_statement(
            "INSERT INTO sqlite_master(type,name,tbl_name,rootpage,sql) "
            "VALUES('table','tweets_fts','tweets_fts',0,'...');"
        )

    def test_fts_table(self):
        assert _is_fts_statement("CREATE VIRTUAL TABLE tweets_fts USING fts5(...);")
        assert _is_fts_statement("INSERT INTO tweets_fts VALUES(...);")

    def test_fts_shadow_tables(self):
        assert _is_fts_statement("CREATE TABLE 'tweets_fts_config'(...);")
        assert _is_fts_statement("INSERT INTO 'tweets_fts_content' VALUES(...);")
        assert _is_fts_statement("CREATE TABLE 'tweets_fts_data'(...);")
        assert _is_fts_statement("CREATE TABLE 'tweets_fts_docsize'(...);")
        assert _is_fts_statement("CREATE TABLE 'tweets_fts_idx'(...);")

    def test_fts_triggers(self):
        assert _is_fts_statement("CREATE TRIGGER tweets_ai AFTER INSERT ON tweets ...")
        assert _is_fts_statement("CREATE TRIGGER tweets_ad AFTER DELETE ON tweets ...")
        assert _is_fts_statement("CREATE TRIGGER tweets_au AFTER UPDATE ON tweets ...")

    def test_normal_statements_pass(self):
        assert not _is_fts_statement("CREATE TABLE tweets (...);")
        assert not _is_fts_statement("INSERT INTO tweets VALUES (...);")
        assert not _is_fts_statement("CREATE TABLE accounts (...);")
        assert not _is_fts_statement("BEGIN TRANSACTION;")
        assert not _is_fts_statement("COMMIT;")


class TestDumpSql:
    """Tests for dump_sql()."""

    def test_dump_produces_valid_sql(self, db_path):
        stmts = list(dump_sql(db_path))
        assert len(stmts) > 0
        # Should start with BEGIN and end with COMMIT
        assert stmts[0] == "BEGIN TRANSACTION;"
        assert stmts[-1] == "COMMIT;"

    def test_dump_excludes_fts_statements(self, db_path):
        stmts = list(dump_sql(db_path))
        for stmt in stmts:
            assert "tweets_fts" not in stmt, f"FTS reference in dump: {stmt[:80]}"
            assert "PRAGMA writable_schema" not in stmt
            assert "INSERT INTO sqlite_master" not in stmt
            assert "tweets_ai" not in stmt
            assert "tweets_ad" not in stmt
            assert "tweets_au" not in stmt

    def test_dump_includes_regular_tables(self, db_path):
        sql = "\n".join(dump_sql(db_path))
        assert "CREATE TABLE" in sql
        assert "tweets" in sql
        assert "accounts" in sql

    def test_dump_includes_data(self, db_path):
        sql = "\n".join(dump_sql(db_path))
        assert "INSERT INTO" in sql
        assert "tweet_0" in sql
        assert "user_0" in sql


class TestRestoreSql:
    """Tests for restore_sql()."""

    def test_dump_restore_roundtrip(self, db_path, tmp_path):
        """Dump a db and restore to a new path, verify data matches."""
        sql = "\n".join(dump_sql(db_path))
        restore_path = tmp_path / "restored.db"

        counts = restore_sql(sql, restore_path, backup=False)

        assert counts["tweets"] == 5
        assert counts["accounts"] == 3

        # Verify actual data
        with get_connection(restore_path) as conn:
            cursor = conn.execute("SELECT id FROM tweets ORDER BY id")
            ids = [row[0] for row in cursor.fetchall()]
            assert ids == [f"tweet_{i}" for i in range(5)]

    def test_dump_restore_with_fts_data(self, db_path, tmp_path):
        """Verify FTS search works after dump/restore cycle."""
        sql = "\n".join(dump_sql(db_path))
        restore_path = tmp_path / "restored.db"

        counts = restore_sql(sql, restore_path, backup=False)
        assert counts["fts"] == 5

        # Verify FTS search works
        with get_connection(restore_path) as conn:
            results = search_tweets(conn, "inflation", limit=10)
            assert len(results) == 5

    def test_restore_from_legacy_dump(self, db_path, tmp_path):
        """Test restoring a dump that includes FTS shadow table statements."""
        # Create a "legacy" dump using raw iterdump (includes FTS artifacts)
        conn = sqlite3.connect(db_path)
        legacy_sql = "\n".join(conn.iterdump())
        conn.close()

        # Verify the legacy dump actually has FTS artifacts
        assert "tweets_fts" in legacy_sql

        restore_path = tmp_path / "restored.db"
        counts = restore_sql(legacy_sql, restore_path, backup=False)

        assert counts["tweets"] == 5
        assert counts["accounts"] == 3
        assert counts["fts"] == 5

        # Verify search works
        with get_connection(restore_path) as conn:
            results = search_tweets(conn, "inflation", limit=10)
            assert len(results) == 5

    def test_restore_creates_data_dir(self, tmp_path):
        """Verify parent directory is created if it doesn't exist."""
        db_path_fixture = tmp_path / "source.db"
        init_db(db_path_fixture)

        sql = "\n".join(dump_sql(db_path_fixture))

        nested_path = tmp_path / "a" / "b" / "c" / "restored.db"
        assert not nested_path.parent.exists()

        restore_sql(sql, nested_path, backup=False)

        assert nested_path.exists()

    def test_restore_gz(self, db_path, tmp_path):
        """Verify gzip handling works end-to-end (simulating CLI behavior)."""
        sql = "\n".join(dump_sql(db_path))

        # Write gzipped dump
        gz_path = tmp_path / "backup.sql.gz"
        with gzip.open(gz_path, "wt", encoding="utf-8") as f:
            f.write(sql)

        # Read back like the CLI would
        with gzip.open(gz_path, "rt", encoding="utf-8") as f:
            restored_sql = f.read()

        restore_path = tmp_path / "restored.db"
        counts = restore_sql(restored_sql, restore_path, backup=False)

        assert counts["tweets"] == 5
        assert counts["accounts"] == 3

    def test_restore_backs_up_existing(self, db_path, tmp_path):
        """Verify backup is created when restoring over existing db."""
        sql = "\n".join(dump_sql(db_path))

        # Create an existing db at the restore target
        restore_path = tmp_path / "target.db"
        init_db(restore_path)
        with get_connection(restore_path) as conn:
            insert_tweet(conn, "old_tweet", "old_user", "old content", source="test")
            conn.commit()

        counts = restore_sql(sql, restore_path, backup=True)
        assert counts["tweets"] == 5

        # Backup should exist
        backup_path = restore_path.with_suffix(".db.bak")
        assert backup_path.exists()

        # Backup should have the old data
        with get_connection(backup_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM tweets WHERE id = 'old_tweet'")
            assert cursor.fetchone()[0] == 1
