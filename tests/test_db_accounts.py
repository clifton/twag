"""Tests for twag.db.accounts."""

import sqlite3

import pytest

from twag.db.accounts import (
    apply_account_decay,
    boost_account,
    demote_account,
    get_accounts,
    mute_account,
    promote_account,
    update_account_stats,
    upsert_account,
)
from twag.db.schema import SCHEMA


@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    yield conn
    conn.close()


class TestUpsertAccount:
    def test_insert(self, db):
        upsert_account(db, "alice", display_name="Alice", tier=1)
        db.commit()
        row = db.execute("SELECT * FROM accounts WHERE handle = 'alice'").fetchone()
        assert row["display_name"] == "Alice"
        assert row["tier"] == 1

    def test_update_preserves_lower_tier(self, db):
        upsert_account(db, "bob", tier=1)
        db.commit()
        upsert_account(db, "bob", tier=2)
        db.commit()
        row = db.execute("SELECT * FROM accounts WHERE handle = 'bob'").fetchone()
        assert row["tier"] == 1  # tier 1 < tier 2, so preserved

    def test_strips_at_sign(self, db):
        upsert_account(db, "@charlie")
        db.commit()
        row = db.execute("SELECT * FROM accounts WHERE handle = 'charlie'").fetchone()
        assert row is not None


class TestGetAccounts:
    def test_filter_by_tier(self, db):
        upsert_account(db, "t1", tier=1)
        upsert_account(db, "t2", tier=2)
        db.commit()
        results = get_accounts(db, tier=1)
        assert len(results) == 1
        assert results[0]["handle"] == "t1"

    def test_exclude_muted(self, db):
        upsert_account(db, "active")
        upsert_account(db, "muted_user")
        mute_account(db, "muted_user")
        db.commit()
        results = get_accounts(db, include_muted=False)
        handles = [r["handle"] for r in results]
        assert "muted_user" not in handles

    def test_include_muted(self, db):
        upsert_account(db, "active")
        upsert_account(db, "muted_user")
        mute_account(db, "muted_user")
        db.commit()
        results = get_accounts(db, include_muted=True)
        handles = [r["handle"] for r in results]
        assert "muted_user" in handles

    def test_order_by_last_fetched(self, db):
        upsert_account(db, "first")
        upsert_account(db, "second")
        db.execute("UPDATE accounts SET last_fetched_at = '2025-01-01' WHERE handle = 'second'")
        db.commit()
        results = get_accounts(db, order_by_last_fetched=True)
        # 'first' has NULL last_fetched_at -> sorts first (coalesced to 1970)
        assert results[0]["handle"] == "first"

    def test_limit(self, db):
        for i in range(5):
            upsert_account(db, f"user{i}")
        db.commit()
        results = get_accounts(db, limit=2)
        assert len(results) == 2


class TestPromoteDemote:
    def test_promote(self, db):
        upsert_account(db, "user", tier=2)
        promote_account(db, "user")
        db.commit()
        row = db.execute("SELECT tier FROM accounts WHERE handle = 'user'").fetchone()
        assert row["tier"] == 1

    def test_demote(self, db):
        upsert_account(db, "user", tier=1)
        demote_account(db, "user", tier=3)
        db.commit()
        row = db.execute("SELECT tier FROM accounts WHERE handle = 'user'").fetchone()
        assert row["tier"] == 3


class TestMuteAccount:
    def test_mute(self, db):
        upsert_account(db, "user")
        mute_account(db, "user")
        db.commit()
        row = db.execute("SELECT muted FROM accounts WHERE handle = 'user'").fetchone()
        assert row["muted"] == 1


class TestBoostAccount:
    def test_boost(self, db):
        upsert_account(db, "user")
        boost_account(db, "user", amount=10)
        db.commit()
        row = db.execute("SELECT weight FROM accounts WHERE handle = 'user'").fetchone()
        assert row["weight"] == 60.0  # default 50 + 10

    def test_weight_capped_at_100(self, db):
        upsert_account(db, "user")
        boost_account(db, "user", amount=200)
        db.commit()
        row = db.execute("SELECT weight FROM accounts WHERE handle = 'user'").fetchone()
        assert row["weight"] == 100.0


class TestApplyAccountDecay:
    def test_decays_stale_accounts(self, db):
        upsert_account(db, "stale")
        db.commit()
        count = apply_account_decay(db, decay_rate=0.1)
        db.commit()
        assert count == 1
        row = db.execute("SELECT weight FROM accounts WHERE handle = 'stale'").fetchone()
        assert row["weight"] == 45.0  # 50 * 0.9

    def test_floor_at_10(self, db):
        upsert_account(db, "low")
        db.execute("UPDATE accounts SET weight = 10 WHERE handle = 'low'")
        db.commit()
        apply_account_decay(db, decay_rate=0.5)
        db.commit()
        row = db.execute("SELECT weight FROM accounts WHERE handle = 'low'").fetchone()
        assert row["weight"] == 10.0

    def test_skips_recently_active(self, db):
        upsert_account(db, "active")
        db.execute("UPDATE accounts SET last_high_signal_at = datetime('now') WHERE handle = 'active'")
        db.commit()
        count = apply_account_decay(db, decay_rate=0.1)
        assert count == 0


class TestUpdateAccountStats:
    def test_increments_stats(self, db):
        upsert_account(db, "user")
        db.commit()
        update_account_stats(db, "user", score=7.0, is_high_signal=True)
        db.commit()
        row = db.execute(
            "SELECT tweets_seen, tweets_kept, last_high_signal_at FROM accounts WHERE handle = 'user'"
        ).fetchone()
        assert row["tweets_seen"] == 1
        assert row["tweets_kept"] == 1
        assert row["last_high_signal_at"] is not None

    def test_low_score_not_kept(self, db):
        upsert_account(db, "user")
        db.commit()
        update_account_stats(db, "user", score=3.0)
        db.commit()
        row = db.execute("SELECT tweets_kept FROM accounts WHERE handle = 'user'").fetchone()
        assert row["tweets_kept"] == 0
