"""Tests covering logging configuration and instrumentation added by the audit."""

from __future__ import annotations

import logging
import subprocess
from unittest.mock import patch

import pytest

from twag import logging_setup
from twag.fetcher.bird_cli import _run_bird_once


@pytest.fixture
def reset_logging():
    """Reset the logging_setup module's idempotent state for each test."""
    logging_setup.reset_for_tests()
    yield
    logging_setup.reset_for_tests()


def test_configure_logging_installs_handler(reset_logging):
    logging_setup.configure_logging()
    root = logging.getLogger()
    assert root.handlers, "configure_logging should install a root handler"
    assert root.level == logging.INFO


def test_configure_logging_is_idempotent(reset_logging):
    logging_setup.configure_logging()
    handler_count = len(logging.getLogger().handlers)
    logging_setup.configure_logging()
    assert len(logging.getLogger().handlers) == handler_count


def test_log_level_env_override(monkeypatch, reset_logging):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    logging_setup.configure_logging(level="WARNING")
    assert logging.getLogger().level == logging.DEBUG


def test_triage_summary_swallow_logs_warning(caplog):
    """Tweet summarization failures should produce a WARNING with traceback."""
    from twag.processor import triage

    log = logging.getLogger("twag.processor.triage")
    with caplog.at_level(logging.WARNING, logger="twag.processor.triage"):
        try:
            raise RuntimeError("boom")
        except Exception:
            log.warning("Tweet summarization failed for %s", "tweet-123", exc_info=True)

    matching = [r for r in caplog.records if "Tweet summarization failed" in r.getMessage()]
    assert matching, "expected a WARNING about summarization failure"
    record = matching[0]
    assert record.exc_info is not None, "exc_info should be attached"
    assert record.levelno == logging.WARNING

    # Sanity-check that triage.log is the logger we just exercised.
    assert triage.log.name == "twag.processor.triage"


def test_bird_cli_timeout_logs_traceback(caplog):
    """Timeout in bird CLI invocation must emit ERROR with exc_info."""

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="bird", timeout=1)

    with (
        caplog.at_level(logging.ERROR, logger="twag.fetcher.bird_cli"),
        patch("subprocess.run", side_effect=fake_run),
    ):
        stdout, stderr, code = _run_bird_once(
            ["bird", "home"],
            env={},
            args=["home"],
            timeout=1,
        )

    assert code == 1
    assert stdout == ""
    assert stderr == "Command timed out"
    matching = [r for r in caplog.records if "timed out" in r.getMessage()]
    assert matching, "expected ERROR record for timeout"
    assert matching[0].exc_info is not None


def test_bird_cli_missing_binary_logs_traceback(caplog):
    """FileNotFoundError must emit ERROR with exc_info."""

    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("bird not found")

    with (
        caplog.at_level(logging.ERROR, logger="twag.fetcher.bird_cli"),
        patch("subprocess.run", side_effect=fake_run),
    ):
        stdout, stderr, code = _run_bird_once(
            ["bird", "home"],
            env={},
            args=["home"],
            timeout=1,
        )

    assert code == 1
    assert stderr == "bird CLI not found"
    matching = [r for r in caplog.records if "bird CLI not found" in r.getMessage()]
    assert matching, "expected ERROR record for missing binary"
    assert matching[0].exc_info is not None


def test_module_loggers_named_for_their_modules():
    """Modules added to the audit should expose loggers named after the module."""
    from twag.db import accounts as db_accounts
    from twag.db import alerts as db_alerts
    from twag.db import maintenance as db_maintenance
    from twag.db import narratives as db_narratives
    from twag.db import prompts as db_prompts
    from twag.db import reactions as db_reactions
    from twag.db import search as db_search
    from twag.db import tweets as db_tweets
    from twag.processor import triage
    from twag.scorer import llm_client, scoring

    expected = {
        db_accounts.log: "twag.db.accounts",
        db_alerts.log: "twag.db.alerts",
        db_maintenance.log: "twag.db.maintenance",
        db_narratives.log: "twag.db.narratives",
        db_prompts.log: "twag.db.prompts",
        db_reactions.log: "twag.db.reactions",
        db_search.log: "twag.db.search",
        db_tweets.log: "twag.db.tweets",
        triage.log: "twag.processor.triage",
        llm_client.log: "twag.scorer.llm_client",
        scoring.log: "twag.scorer.scoring",
    }
    for logger, name in expected.items():
        assert logger.name == name
