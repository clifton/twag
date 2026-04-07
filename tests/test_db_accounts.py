"""Tests for twag.db.accounts — account CRUD with in-memory SQLite."""

import sqlite3
from datetime import datetime, timezone

from twag.db.accounts import (
    apply_account_decay,
    boost_account,
    demote_account,
    get_accounts,
    mute_account,
    promote_account,
    upsert_account,
)


def _make_db() -> sqlite3.Connection:
    """Create an in-memory SQLite database with the accounts schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
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
        )
    """)
    return conn


class TestUpsertAccount:
    def test_insert_new(self):
        conn = _make_db()
        upsert_account(conn, "alice", display_name="Alice", tier=1, category="tech")
        row = conn.execute("SELECT * FROM accounts WHERE handle='alice'").fetchone()
        assert row["display_name"] == "Alice"
        assert row["tier"] == 1
        assert row["category"] == "tech"

    def test_update_keeps_lower_tier(self):
        conn = _make_db()
        upsert_account(conn, "bob", tier=1)
        upsert_account(conn, "bob", tier=2)
        row = conn.execute("SELECT tier FROM accounts WHERE handle='bob'").fetchone()
        assert row["tier"] == 1  # Lower tier wins

    def test_update_display_name_coalesce(self):
        conn = _make_db()
        upsert_account(conn, "carol", display_name="Carol")
        upsert_account(conn, "carol", display_name=None)
        row = conn.execute("SELECT display_name FROM accounts WHERE handle='carol'").fetchone()
        assert row["display_name"] == "Carol"  # Original preserved

    def test_strips_at_prefix(self):
        conn = _make_db()
        upsert_account(conn, "@dave")
        row = conn.execute("SELECT * FROM accounts WHERE handle='dave'").fetchone()
        assert row is not None


class TestGetAccounts:
    def test_tier_filter(self):
        conn = _make_db()
        upsert_account(conn, "t1", tier=1)
        upsert_account(conn, "t2", tier=2)
        rows = get_accounts(conn, tier=1)
        handles = [r["handle"] for r in rows]
        assert "t1" in handles
        assert "t2" not in handles

    def test_muted_filter(self):
        conn = _make_db()
        upsert_account(conn, "active")
        upsert_account(conn, "muted_acc")
        mute_account(conn, "muted_acc")
        rows = get_accounts(conn, include_muted=False)
        handles = [r["handle"] for r in rows]
        assert "active" in handles
        assert "muted_acc" not in handles

    def test_include_muted(self):
        conn = _make_db()
        upsert_account(conn, "active")
        upsert_account(conn, "muted_acc")
        mute_account(conn, "muted_acc")
        rows = get_accounts(conn, include_muted=True)
        handles = [r["handle"] for r in rows]
        assert "muted_acc" in handles

    def test_ordering_default(self):
        conn = _make_db()
        upsert_account(conn, "tier2", tier=2)
        upsert_account(conn, "tier1", tier=1)
        rows = get_accounts(conn)
        assert rows[0]["handle"] == "tier1"

    def test_limit(self):
        conn = _make_db()
        for i in range(5):
            upsert_account(conn, f"user{i}")
        rows = get_accounts(conn, limit=2)
        assert len(rows) == 2


class TestPromoteAccount:
    def test_promote_to_tier1(self):
        conn = _make_db()
        upsert_account(conn, "user", tier=2)
        promote_account(conn, "user")
        row = conn.execute("SELECT tier FROM accounts WHERE handle='user'").fetchone()
        assert row["tier"] == 1


class TestDemoteAccount:
    def test_demote_to_tier2(self):
        conn = _make_db()
        upsert_account(conn, "user", tier=1)
        demote_account(conn, "user", tier=2)
        row = conn.execute("SELECT tier FROM accounts WHERE handle='user'").fetchone()
        assert row["tier"] == 2


class TestMuteAccount:
    def test_mute_sets_flag(self):
        conn = _make_db()
        upsert_account(conn, "user")
        mute_account(conn, "user")
        row = conn.execute("SELECT muted FROM accounts WHERE handle='user'").fetchone()
        assert row["muted"] == 1


class TestBoostAccount:
    def test_boost_increases_weight(self):
        conn = _make_db()
        upsert_account(conn, "user")
        boost_account(conn, "user", amount=10.0)
        row = conn.execute("SELECT weight FROM accounts WHERE handle='user'").fetchone()
        assert row["weight"] == 60.0

    def test_boost_clamped_at_100(self):
        conn = _make_db()
        upsert_account(conn, "user")  # default weight 50
        boost_account(conn, "user", amount=60.0)
        row = conn.execute("SELECT weight FROM accounts WHERE handle='user'").fetchone()
        assert row["weight"] == 100.0


class TestApplyAccountDecay:
    def test_decay_reduces_weight(self):
        conn = _make_db()
        upsert_account(conn, "user")
        count = apply_account_decay(conn, decay_rate=0.1)
        assert count >= 1
        row = conn.execute("SELECT weight FROM accounts WHERE handle='user'").fetchone()
        assert row["weight"] == 45.0  # 50 * (1 - 0.1)

    def test_decay_floor_at_10(self):
        conn = _make_db()
        upsert_account(conn, "user")
        conn.execute("UPDATE accounts SET weight=10 WHERE handle='user'")
        apply_account_decay(conn, decay_rate=0.5)
        row = conn.execute("SELECT weight FROM accounts WHERE handle='user'").fetchone()
        assert row["weight"] == 10.0  # Floor

    def test_recent_high_signal_skipped(self):
        conn = _make_db()
        upsert_account(conn, "active")
        recent = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE accounts SET last_high_signal_at=? WHERE handle='active'", (recent,))
        apply_account_decay(conn, decay_rate=0.1)
        row = conn.execute("SELECT weight FROM accounts WHERE handle='active'").fetchone()
        assert row["weight"] == 50.0  # Unchanged
