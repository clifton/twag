"""Tests for twag.db.accounts — account CRUD with in-memory SQLite."""

import sqlite3

import pytest

from twag.db.accounts import (
    apply_account_decay,
    boost_account,
    demote_account,
    get_accounts,
    mute_account,
    promote_account,
    upsert_account,
)

ACCOUNTS_SCHEMA = """
CREATE TABLE accounts (
    handle TEXT PRIMARY KEY,
    display_name TEXT,
    tier INTEGER DEFAULT 2,
    weight REAL DEFAULT 50.0,
    category TEXT,
    tweets_seen INTEGER DEFAULT 0,
    tweets_kept INTEGER DEFAULT 0,
    avg_relevance_score REAL,
    last_high_signal_at TIMESTAMP,
    last_fetched_at TIMESTAMP,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    auto_promoted INTEGER DEFAULT 0,
    muted INTEGER DEFAULT 0
);
"""


@pytest.fixture
def conn():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(ACCOUNTS_SCHEMA)
    yield db
    db.close()


class TestUpsertAccount:
    def test_insert_new(self, conn):
        upsert_account(conn, "alice", display_name="Alice", tier=1)
        conn.commit()
        row = conn.execute("SELECT * FROM accounts WHERE handle = 'alice'").fetchone()
        assert row is not None
        assert row["display_name"] == "Alice"
        assert row["tier"] == 1

    def test_update_preserves_display_name(self, conn):
        upsert_account(conn, "bob", display_name="Bob", tier=2)
        conn.commit()
        # Update without display_name — should keep "Bob"
        upsert_account(conn, "bob", display_name=None, tier=2)
        conn.commit()
        row = conn.execute("SELECT * FROM accounts WHERE handle = 'bob'").fetchone()
        assert row["display_name"] == "Bob"

    def test_update_tier_only_promotes(self, conn):
        upsert_account(conn, "charlie", tier=2)
        conn.commit()
        # tier=1 is better (lower) than 2, so should update
        upsert_account(conn, "charlie", tier=1)
        conn.commit()
        row = conn.execute("SELECT * FROM accounts WHERE handle = 'charlie'").fetchone()
        assert row["tier"] == 1

    def test_update_tier_no_demote(self, conn):
        upsert_account(conn, "dave", tier=1)
        conn.commit()
        # tier=2 is worse (higher) than 1, should NOT update
        upsert_account(conn, "dave", tier=2)
        conn.commit()
        row = conn.execute("SELECT * FROM accounts WHERE handle = 'dave'").fetchone()
        assert row["tier"] == 1

    def test_strips_at_sign(self, conn):
        upsert_account(conn, "@testuser")
        conn.commit()
        row = conn.execute("SELECT * FROM accounts WHERE handle = 'testuser'").fetchone()
        assert row is not None


class TestGetAccounts:
    def _seed(self, conn):
        upsert_account(conn, "tier1", tier=1)
        upsert_account(conn, "tier2a", tier=2)
        upsert_account(conn, "tier2b", tier=2)
        conn.commit()

    def test_tier_filter(self, conn):
        self._seed(conn)
        rows = get_accounts(conn, tier=1)
        assert len(rows) == 1
        assert rows[0]["handle"] == "tier1"

    def test_muted_excluded_by_default(self, conn):
        self._seed(conn)
        mute_account(conn, "tier2a")
        conn.commit()
        rows = get_accounts(conn)
        handles = {r["handle"] for r in rows}
        assert "tier2a" not in handles

    def test_include_muted(self, conn):
        self._seed(conn)
        mute_account(conn, "tier2a")
        conn.commit()
        rows = get_accounts(conn, include_muted=True)
        handles = {r["handle"] for r in rows}
        assert "tier2a" in handles

    def test_ordering_default(self, conn):
        self._seed(conn)
        rows = get_accounts(conn)
        # Default: tier ASC, weight DESC → tier1 first
        assert rows[0]["handle"] == "tier1"

    def test_limit(self, conn):
        self._seed(conn)
        rows = get_accounts(conn, limit=2)
        assert len(rows) == 2


class TestPromoteAccount:
    def test_promote_to_tier1(self, conn):
        upsert_account(conn, "user1", tier=2)
        conn.commit()
        promote_account(conn, "user1")
        conn.commit()
        row = conn.execute("SELECT tier FROM accounts WHERE handle = 'user1'").fetchone()
        assert row["tier"] == 1


class TestDemoteAccount:
    def test_demote(self, conn):
        upsert_account(conn, "user1", tier=1)
        conn.commit()
        demote_account(conn, "user1", tier=3)
        conn.commit()
        row = conn.execute("SELECT tier FROM accounts WHERE handle = 'user1'").fetchone()
        assert row["tier"] == 3


class TestMuteAccount:
    def test_mute(self, conn):
        upsert_account(conn, "user1")
        conn.commit()
        mute_account(conn, "user1")
        conn.commit()
        row = conn.execute("SELECT muted FROM accounts WHERE handle = 'user1'").fetchone()
        assert row["muted"] == 1


class TestBoostAccount:
    def test_boost_increases_weight(self, conn):
        upsert_account(conn, "user1")
        conn.commit()
        boost_account(conn, "user1", amount=10.0)
        conn.commit()
        row = conn.execute("SELECT weight FROM accounts WHERE handle = 'user1'").fetchone()
        assert row["weight"] == 60.0

    def test_boost_clamps_at_100(self, conn):
        upsert_account(conn, "user1")
        conn.commit()
        boost_account(conn, "user1", amount=200.0)
        conn.commit()
        row = conn.execute("SELECT weight FROM accounts WHERE handle = 'user1'").fetchone()
        assert row["weight"] == 100.0


class TestApplyAccountDecay:
    def test_decay_reduces_weight(self, conn):
        upsert_account(conn, "user1")
        conn.commit()
        affected = apply_account_decay(conn, decay_rate=0.1)
        conn.commit()
        assert affected >= 1
        row = conn.execute("SELECT weight FROM accounts WHERE handle = 'user1'").fetchone()
        assert row["weight"] == pytest.approx(45.0)

    def test_decay_skips_recent_high_signal(self, conn):
        upsert_account(conn, "active")
        conn.commit()
        # Set a recent high signal timestamp
        conn.execute("UPDATE accounts SET last_high_signal_at = datetime('now') WHERE handle = 'active'")
        conn.commit()
        original = conn.execute("SELECT weight FROM accounts WHERE handle = 'active'").fetchone()
        apply_account_decay(conn, decay_rate=0.1)
        conn.commit()
        after = conn.execute("SELECT weight FROM accounts WHERE handle = 'active'").fetchone()
        assert after["weight"] == original["weight"]

    def test_decay_floor_at_10(self, conn):
        upsert_account(conn, "low")
        conn.commit()
        conn.execute("UPDATE accounts SET weight = 10.0 WHERE handle = 'low'")
        conn.commit()
        apply_account_decay(conn, decay_rate=0.5)
        conn.commit()
        row = conn.execute("SELECT weight FROM accounts WHERE handle = 'low'").fetchone()
        assert row["weight"] == 10.0
