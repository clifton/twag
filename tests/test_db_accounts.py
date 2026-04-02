"""Tests for twag.db.accounts — account CRUD with in-memory SQLite."""

from twag.db import get_connection, init_db
from twag.db.accounts import (
    apply_account_decay,
    boost_account,
    demote_account,
    get_accounts,
    mute_account,
    promote_account,
    upsert_account,
)


def _setup_db(tmp_path):
    db_path = tmp_path / "test_accounts.db"
    init_db(db_path)
    return db_path


def test_upsert_and_get_account(tmp_path):
    db_path = _setup_db(tmp_path)
    with get_connection(db_path) as conn:
        upsert_account(conn, "alice", display_name="Alice", tier=1, category="macro")
        conn.commit()
        accounts = get_accounts(conn)
        assert len(accounts) == 1
        assert accounts[0]["handle"] == "alice"
        assert accounts[0]["display_name"] == "Alice"
        assert accounts[0]["tier"] == 1


def test_upsert_strips_at_sign(tmp_path):
    db_path = _setup_db(tmp_path)
    with get_connection(db_path) as conn:
        upsert_account(conn, "@bob")
        conn.commit()
        accounts = get_accounts(conn)
        assert accounts[0]["handle"] == "bob"


def test_upsert_does_not_overwrite_name_with_none(tmp_path):
    db_path = _setup_db(tmp_path)
    with get_connection(db_path) as conn:
        upsert_account(conn, "carol", display_name="Carol")
        conn.commit()
        upsert_account(conn, "carol", display_name=None)
        conn.commit()
        accounts = get_accounts(conn)
        assert accounts[0]["display_name"] == "Carol"


def test_upsert_tier_only_decreases(tmp_path):
    db_path = _setup_db(tmp_path)
    with get_connection(db_path) as conn:
        upsert_account(conn, "dave", tier=1)
        conn.commit()
        upsert_account(conn, "dave", tier=2)
        conn.commit()
        accounts = get_accounts(conn)
        assert accounts[0]["tier"] == 1  # tier=2 should not replace tier=1


def test_promote_account(tmp_path):
    db_path = _setup_db(tmp_path)
    with get_connection(db_path) as conn:
        upsert_account(conn, "eve", tier=2)
        conn.commit()
        promote_account(conn, "eve")
        conn.commit()
        accounts = get_accounts(conn, tier=1)
        assert len(accounts) == 1
        assert accounts[0]["handle"] == "eve"


def test_mute_account(tmp_path):
    db_path = _setup_db(tmp_path)
    with get_connection(db_path) as conn:
        upsert_account(conn, "frank")
        conn.commit()
        mute_account(conn, "frank")
        conn.commit()
        # Muted accounts excluded by default
        assert len(get_accounts(conn)) == 0
        # But included with flag
        assert len(get_accounts(conn, include_muted=True)) == 1


def test_demote_account(tmp_path):
    db_path = _setup_db(tmp_path)
    with get_connection(db_path) as conn:
        upsert_account(conn, "grace", tier=1)
        conn.commit()
        demote_account(conn, "grace", tier=3)
        conn.commit()
        accounts = get_accounts(conn)
        assert accounts[0]["tier"] == 3


def test_boost_account(tmp_path):
    db_path = _setup_db(tmp_path)
    with get_connection(db_path) as conn:
        upsert_account(conn, "hank")
        conn.commit()
        original_weight = get_accounts(conn)[0]["weight"]
        boost_account(conn, "hank", amount=10.0)
        conn.commit()
        new_weight = get_accounts(conn)[0]["weight"]
        assert new_weight == original_weight + 10.0


def test_boost_account_clamped_at_100(tmp_path):
    db_path = _setup_db(tmp_path)
    with get_connection(db_path) as conn:
        upsert_account(conn, "irene")
        conn.commit()
        boost_account(conn, "irene", amount=200.0)
        conn.commit()
        assert get_accounts(conn)[0]["weight"] == 100.0


def test_apply_account_decay(tmp_path):
    db_path = _setup_db(tmp_path)
    with get_connection(db_path) as conn:
        upsert_account(conn, "jack")
        conn.commit()
        original_weight = get_accounts(conn)[0]["weight"]
        count = apply_account_decay(conn, decay_rate=0.1)
        conn.commit()
        assert count >= 1
        new_weight = get_accounts(conn)[0]["weight"]
        assert new_weight < original_weight


def test_get_accounts_filter_by_tier(tmp_path):
    db_path = _setup_db(tmp_path)
    with get_connection(db_path) as conn:
        upsert_account(conn, "t1_user", tier=1)
        upsert_account(conn, "t2_user", tier=2)
        conn.commit()
        tier1 = get_accounts(conn, tier=1)
        assert len(tier1) == 1
        assert tier1[0]["handle"] == "t1_user"
