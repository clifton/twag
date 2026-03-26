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
from twag.db.schema import SCHEMA


@pytest.fixture
def conn():
    """In-memory SQLite with schema applied."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    yield db
    db.close()


def _get_account(conn, handle):
    row = conn.execute("SELECT * FROM accounts WHERE handle = ?", (handle,)).fetchone()
    return dict(row) if row else None


class TestUpsertAccount:
    def test_insert_new(self, conn):
        upsert_account(conn, "alice", display_name="Alice", tier=1)
        acct = _get_account(conn, "alice")
        assert acct is not None
        assert acct["display_name"] == "Alice"
        assert acct["tier"] == 1

    def test_strips_at_prefix(self, conn):
        upsert_account(conn, "@bob")
        assert _get_account(conn, "bob") is not None

    def test_conflict_only_lowers_tier(self, conn):
        upsert_account(conn, "carol", tier=2)
        upsert_account(conn, "carol", tier=1)
        assert _get_account(conn, "carol")["tier"] == 1
        # Trying to raise tier back to 2 should keep 1
        upsert_account(conn, "carol", tier=2)
        assert _get_account(conn, "carol")["tier"] == 1


class TestGetAccounts:
    def test_filter_by_tier(self, conn):
        upsert_account(conn, "t1", tier=1)
        upsert_account(conn, "t2", tier=2)
        rows = get_accounts(conn, tier=1)
        handles = [r["handle"] for r in rows]
        assert "t1" in handles
        assert "t2" not in handles

    def test_exclude_muted(self, conn):
        upsert_account(conn, "loud")
        upsert_account(conn, "quiet")
        mute_account(conn, "quiet")
        rows = get_accounts(conn, include_muted=False)
        handles = [r["handle"] for r in rows]
        assert "quiet" not in handles
        assert "loud" in handles

    def test_include_muted(self, conn):
        upsert_account(conn, "muted_user")
        mute_account(conn, "muted_user")
        rows = get_accounts(conn, include_muted=True)
        handles = [r["handle"] for r in rows]
        assert "muted_user" in handles

    def test_limit(self, conn):
        for i in range(5):
            upsert_account(conn, f"user{i}")
        rows = get_accounts(conn, limit=2)
        assert len(rows) == 2


class TestBoostAccount:
    def test_boost_increases_weight(self, conn):
        upsert_account(conn, "alice")
        original = _get_account(conn, "alice")["weight"]
        boost_account(conn, "alice", amount=10)
        assert _get_account(conn, "alice")["weight"] == original + 10

    def test_boost_caps_at_100(self, conn):
        upsert_account(conn, "alice")
        boost_account(conn, "alice", amount=200)
        assert _get_account(conn, "alice")["weight"] == 100


class TestPromoteAccount:
    def test_promote_sets_tier_1(self, conn):
        upsert_account(conn, "alice", tier=2)
        promote_account(conn, "alice")
        assert _get_account(conn, "alice")["tier"] == 1


class TestMuteAccount:
    def test_mute_sets_flag(self, conn):
        upsert_account(conn, "alice")
        assert _get_account(conn, "alice")["muted"] == 0
        mute_account(conn, "alice")
        assert _get_account(conn, "alice")["muted"] == 1


class TestDemoteAccount:
    def test_demote_sets_tier(self, conn):
        upsert_account(conn, "alice", tier=1)
        demote_account(conn, "alice", tier=3)
        assert _get_account(conn, "alice")["tier"] == 3


class TestApplyAccountDecay:
    def test_decay_reduces_weight(self, conn):
        upsert_account(conn, "idle")
        original = _get_account(conn, "idle")["weight"]
        affected = apply_account_decay(conn, decay_rate=0.1)
        assert affected >= 1
        new_weight = _get_account(conn, "idle")["weight"]
        assert new_weight == pytest.approx(original * 0.9)

    def test_decay_floors_at_10(self, conn):
        upsert_account(conn, "low")
        # Set weight low
        conn.execute("UPDATE accounts SET weight = 11 WHERE handle = 'low'")
        apply_account_decay(conn, decay_rate=0.5)
        assert _get_account(conn, "low")["weight"] >= 10
