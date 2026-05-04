"""CLI tests for single-status process behavior."""

from contextlib import contextmanager
from types import SimpleNamespace

from click.testing import CliRunner

from twag.cli import cli


@contextmanager
def _fake_connection(readonly=False):
    yield object()


def test_process_status_id_fast_path(monkeypatch):
    """`twag process <status>` should process exactly one DB row."""
    import twag.cli.process as cli_mod
    import twag.processor as processor_mod

    calls: dict[str, object] = {}

    def _fake_process_unprocessed(
        *,
        limit=100,
        dry_run=False,
        triage_model=None,
        rows=None,
        progress_cb=None,
        status_cb=None,
        total_cb=None,
    ):
        calls["limit"] = limit
        calls["rows"] = rows
        if status_cb:
            status_cb("Saving @test_user")
        if progress_cb:
            progress_cb(1)
        return []

    monkeypatch.setattr(cli_mod, "init_db", lambda: None)
    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(
        cli_mod,
        "get_tweet_by_id",
        lambda _conn, tweet_id: {
            "id": tweet_id,
            "author_handle": "test_user",
            "content": "Google capex",
            "processed_at": None,
        },
    )
    monkeypatch.setattr(processor_mod, "process_unprocessed", _fake_process_unprocessed)

    runner = CliRunner()
    result = runner.invoke(cli, ["process", "2019488673935552978"])

    assert result.exit_code == 0
    assert "Processing status 2019488673935552978..." in result.output
    assert "No unprocessed tweets found." in result.output
    assert "Skipping dependency reprocessing for single-status mode." not in result.output
    assert calls["limit"] == 250
    assert isinstance(calls["rows"], list)
    assert len(calls["rows"]) == 1
    assert calls["rows"][0]["id"] == "2019488673935552978"


def test_process_status_url_normalized(monkeypatch):
    """Status URLs should normalize to the numeric tweet ID."""
    import twag.cli.process as cli_mod
    import twag.processor as processor_mod

    seen: dict[str, str] = {}

    def _fake_get_tweet_by_id(_conn, tweet_id):
        seen["tweet_id"] = tweet_id
        return {
            "id": tweet_id,
            "author_handle": "test_user",
            "content": "Google capex",
            "processed_at": None,
        }

    monkeypatch.setattr(cli_mod, "init_db", lambda: None)
    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_tweet_by_id", _fake_get_tweet_by_id)
    monkeypatch.setattr(
        processor_mod,
        "process_unprocessed",
        lambda **kwargs: [],
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["process", "https://x.com/test_user/status/2019488673935552978"])

    assert result.exit_code == 0
    assert seen["tweet_id"] == "2019488673935552978"


def test_process_status_id_not_found(monkeypatch):
    """Single-status process should fail clearly when tweet is not stored."""
    import twag.cli.process as cli_mod

    monkeypatch.setattr(cli_mod, "init_db", lambda: None)
    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_tweet_by_id", lambda _conn, _tweet_id: None)

    runner = CliRunner()
    result = runner.invoke(cli, ["process", "999"])

    assert result.exit_code == 1
    assert "Status not found in database: 999" in result.output
    assert "twag fetch 999" in result.output


def test_process_skips_notifications_by_default(monkeypatch):
    """`twag process` should not notify unless `--notify` is passed."""
    import twag.cli.process as cli_mod
    import twag.notifier as notifier_mod
    import twag.processor as processor_mod

    notified: list[str] = []

    class _FakeCursor:
        def fetchone(self):
            return {"content": "Google capex", "author_handle": "test_user"}

    class _FakeConn:
        def execute(self, *_args, **_kwargs):
            return _FakeCursor()

    @contextmanager
    def _fake_conn_with_execute(readonly=False):
        yield _FakeConn()

    monkeypatch.setattr(cli_mod, "init_db", lambda: None)
    monkeypatch.setattr(cli_mod, "get_connection", _fake_conn_with_execute)
    monkeypatch.setattr(
        cli_mod,
        "get_unprocessed_tweets",
        lambda _conn, limit=250: [
            {
                "id": "2019488673935552978",
                "author_handle": "test_user",
                "content": "Google capex",
                "processed_at": None,
            },
        ],
    )
    monkeypatch.setattr(
        processor_mod,
        "process_unprocessed",
        lambda **kwargs: [
            SimpleNamespace(
                tweet_id="2019488673935552978",
                score=8.5,
                categories=["equities"],
                summary="Google capex is accelerating.",
                tickers=["GOOGL"],
            ),
        ],
    )
    reprocess_calls: list[dict] = []
    monkeypatch.setattr(processor_mod, "reprocess_today_quoted", lambda **kwargs: reprocess_calls.append(kwargs) or [])
    monkeypatch.setattr(notifier_mod, "notify_high_signal_tweet", lambda **kwargs: notified.append(kwargs["tweet_id"]))

    runner = CliRunner()

    result = runner.invoke(cli, ["process"])

    assert result.exit_code == 0
    assert notified == []
    assert reprocess_calls == []


def test_process_notifies_when_explicitly_enabled(monkeypatch):
    """`twag process --notify` should send notifications for high-signal tweets."""
    import twag.cli.process as cli_mod
    import twag.notifier as notifier_mod
    import twag.processor as processor_mod

    notified: list[str] = []

    class _FakeCursor:
        def fetchone(self):
            return {"content": "Google capex", "author_handle": "test_user"}

    class _FakeConn:
        def execute(self, *_args, **_kwargs):
            return _FakeCursor()

    @contextmanager
    def _fake_conn_with_execute(readonly=False):
        yield _FakeConn()

    monkeypatch.setattr(cli_mod, "init_db", lambda: None)
    monkeypatch.setattr(cli_mod, "get_connection", _fake_conn_with_execute)
    monkeypatch.setattr(
        cli_mod,
        "get_unprocessed_tweets",
        lambda _conn, limit=250: [
            {
                "id": "2019488673935552978",
                "author_handle": "test_user",
                "content": "Google capex",
                "processed_at": None,
            },
        ],
    )
    monkeypatch.setattr(
        processor_mod,
        "process_unprocessed",
        lambda **kwargs: [
            SimpleNamespace(
                tweet_id="2019488673935552978",
                score=8.5,
                categories=["equities"],
                summary="Google capex is accelerating.",
                tickers=["GOOGL"],
            ),
        ],
    )
    reprocess_calls: list[dict] = []
    monkeypatch.setattr(processor_mod, "reprocess_today_quoted", lambda **kwargs: reprocess_calls.append(kwargs) or [])
    monkeypatch.setattr(notifier_mod, "notify_high_signal_tweet", lambda **kwargs: notified.append(kwargs["tweet_id"]))

    runner = CliRunner()

    result = runner.invoke(cli, ["process", "--notify"])

    assert result.exit_code == 0
    assert notified == ["2019488673935552978"]
    assert reprocess_calls == []
