"""CLI tests for tier-1 account fetch behavior."""

import json
import logging
from contextlib import contextmanager
from unittest.mock import MagicMock

from click.testing import CliRunner

from twag.cli import cli
from twag.metrics import get_collector


def test_tier1_missing_user_warns_and_healthy_account_succeeds(monkeypatch, caplog):
    """A missing tier-1 user must not discard healthy accounts or fail the fetch."""
    import twag.cli.fetch as cli_mod
    import twag.config as config_mod
    import twag.db as db_mod
    import twag.fetcher as fetcher_mod
    import twag.fetcher.bird_cli as bird_cli_mod
    import twag.processor as processor_mod

    accounts = [{"handle": "missing"}, {"handle": "healthy"}]
    runner_calls: list[str] = []
    stored: list[tuple[list, str, dict]] = []
    marked_fetched: list[str] = []

    def bird_runner(args: list[str]) -> tuple[str, str, int]:
        handle = args[1]
        runner_calls.append(handle)
        if handle == "@missing":
            return "", "User @missing not found", 1
        return (
            json.dumps([{"id": "healthy-1", "author": {"username": "healthy"}, "text": "still here"}]),
            "",
            0,
        )

    def fetch_user_tweets(handle: str, count: int):
        return bird_cli_mod.fetch_user_tweets(handle, count, bird_runner=bird_runner)

    def store_fetched_tweets(tweets, source, query_params=None, **_kwargs):
        stored.append((tweets, source, query_params or {}))
        return len(tweets), len(tweets)

    @contextmanager
    def get_connection():
        yield MagicMock()

    monkeypatch.setattr(cli_mod, "init_db", lambda: None)
    monkeypatch.setattr(cli_mod, "get_accounts", lambda *_args, **_kwargs: accounts)
    monkeypatch.setattr(cli_mod, "get_connection", get_connection)
    monkeypatch.setattr(config_mod, "load_config", lambda: {"fetch": {"tier1_stagger": None}})
    monkeypatch.setattr(fetcher_mod, "fetch_home_timeline", lambda count: [])
    monkeypatch.setattr(fetcher_mod, "fetch_user_tweets", fetch_user_tweets)
    monkeypatch.setattr(processor_mod, "store_fetched_tweets", store_fetched_tweets)
    monkeypatch.setattr(
        db_mod,
        "update_account_last_fetched",
        lambda _conn, handle: marked_fetched.append(handle),
    )

    metrics = get_collector()
    not_found_before = metrics.counter_value("fetch.accounts.not_found")
    caplog.set_level(logging.WARNING, logger="twag.cli.fetch")

    result = CliRunner().invoke(cli, ["fetch", "--no-bookmarks", "--delay", "0"])

    assert result.exit_code == 0
    assert runner_calls == ["@missing", "@healthy"]
    assert len(stored) == 1
    assert stored[0][0][0].id == "healthy-1"
    assert stored[0][1:] == ("user", {"handle": "healthy", "count": 20})
    assert marked_fetched == ["missing", "healthy"]
    assert "tier-1 account @missing not found; skipping" in caplog.text
    assert metrics.counter_value("fetch.accounts.not_found") == not_found_before + 1
    assert "account(s) failed" not in result.output
    assert "error(s) during fetch" not in result.output
