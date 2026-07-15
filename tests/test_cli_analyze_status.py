"""CLI tests for one-shot status analysis command."""

import json
from contextlib import contextmanager

from click.testing import CliRunner

from twag.cli import cli
from twag.fetcher import Tweet


def _sample_tweet() -> Tweet:
    return Tweet(
        id="2019488673935552978",
        author_handle="test_user",
        author_name="Test User",
        content="Google's $180 Billion Bet",
        created_at=None,
        has_quote=False,
        quote_tweet_id=None,
        in_reply_to_tweet_id=None,
        conversation_id=None,
        has_media=False,
        media_items=[],
        has_link=True,
        is_x_article=True,
        article_title="Google's $180 Billion Bet: Is This the Top?",
        article_preview="Preview",
        article_text="Long article body",
        is_retweet=False,
        retweeted_by_handle=None,
        retweeted_by_name=None,
        original_tweet_id=None,
        original_author_handle=None,
        original_author_name=None,
        original_content=None,
        raw={},
    )


def _sample_reply(tweet_id: str = "reply-1", parent_id: str = "2019488673935552978") -> Tweet:
    return Tweet(
        id=tweet_id,
        author_handle="reply_user",
        author_name="Reply User",
        content="Context reply",
        created_at=None,
        has_quote=False,
        quote_tweet_id=None,
        in_reply_to_tweet_id=parent_id,
        conversation_id=parent_id,
        has_media=False,
        media_items=[],
        has_link=False,
        is_x_article=False,
        article_title=None,
        article_preview=None,
        article_text=None,
        is_retweet=False,
        retweeted_by_handle=None,
        retweeted_by_name=None,
        original_tweet_id=None,
        original_author_handle=None,
        original_author_name=None,
        original_content=None,
        raw={},
    )


@contextmanager
def _fake_connection(readonly=False):
    yield object()


def _sample_row(processed_at: str | None = None) -> dict:
    return {
        "id": "2019488673935552978",
        "author_handle": "test_user",
        "relevance_score": 8.1,
        "signal_tier": "high_signal",
        "category": json.dumps(["equities", "macro"]),
        "tickers": json.dumps(["GOOGL"]),
        "summary": "Google capex scales materially into 2026.",
        "content_summary": None,
        "link_summary": "Link fallback summary",
        "article_summary_short": "Capex step-up is historically large but monetization is improving.",
        "article_primary_points_json": json.dumps(
            [
                {
                    "point": "Capex acceleration is unprecedented",
                    "reasoning": "Spend is stepping higher into 2026.",
                    "evidence": "$180B guide versus prior years.",
                },
            ],
        ),
        "article_action_items_json": json.dumps(
            [
                {
                    "action": "Track hyperscaler ROI disclosures",
                    "trigger": "If capex growth outpaces revenue growth for 2+ quarters",
                    "horizon": "2-4 quarters",
                    "confidence": "medium",
                    "tickers": ["GOOGL", "MSFT"],
                },
            ],
        ),
        "article_top_visual_json": json.dumps(
            {
                "url": "https://pbs.twimg.com/media/HAXmiH6acAEiywu.jpg",
                "kind": "chart",
                "why_important": "Most relevant quantitative visual supporting the thesis.",
                "key_takeaway": "2026 capex bar is the largest in the series.",
            },
        ),
        "media_items": json.dumps(
            [
                {
                    "url": "https://pbs.twimg.com/media/HAXmiH6acAEiywu.jpg",
                    "kind": "chart",
                    "chart": {"insight": "Capex spikes in 2026"},
                },
                {
                    "url": "https://pbs.twimg.com/media/other_photo.jpg",
                    "kind": "photo",
                    "short_description": "office selfie",
                },
            ],
        ),
        "processed_at": processed_at,
    }


def test_analyze_status_success(monkeypatch):
    """Analyze should fetch, process, and print structured article sections."""
    import twag.cli.analyze as analyze_mod
    import twag.fetcher as fetcher_mod
    import twag.processor as processor_mod

    process_calls = {"count": 0, "force_refresh": None}
    row = _sample_row(processed_at=None)

    monkeypatch.setattr(analyze_mod, "init_db", lambda: None)
    monkeypatch.setattr(analyze_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(fetcher_mod, "read_tweet", lambda _status: _sample_tweet())
    monkeypatch.setattr(
        fetcher_mod,
        "fetch_thread",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("thread fetch must be opt-in")),
    )
    monkeypatch.setattr(
        fetcher_mod,
        "fetch_replies",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("reply fetch must be opt-in")),
    )
    monkeypatch.setattr(
        processor_mod,
        "store_fetched_tweets",
        lambda tweets, **kwargs: (len(tweets), len(tweets)),
    )
    monkeypatch.setattr(
        processor_mod,
        "process_unprocessed",
        lambda **kwargs: (
            process_calls.__setitem__("count", process_calls["count"] + 1),
            process_calls.__setitem__("force_refresh", kwargs.get("force_refresh")),
            [],
        )[-1],
    )
    monkeypatch.setattr(analyze_mod, "get_tweet_by_id", lambda _conn, _tweet_id: row)

    runner = CliRunner()
    result = runner.invoke(cli, ["analyze", "https://x.com/test_user/status/2019488673935552978"])

    assert result.exit_code == 0
    assert "Analyzing status 2019488673935552978..." in result.output
    assert "Fetched 1 tweets, 1 new" in result.output
    assert "Article Summary:" in result.output
    assert "Primary Points:" in result.output
    assert "Actionable Items:" in result.output
    assert "Why:" in result.output
    assert "Evidence:" in result.output
    assert "Trigger:" in result.output
    assert "Tickers: GOOGL, MSFT" in result.output
    assert "Visuals:" in result.output
    assert process_calls["count"] == 1
    assert process_calls["force_refresh"] is False


def test_analyze_status_skips_processing_when_already_processed(monkeypatch):
    """Analyze should reuse existing analysis unless --reprocess is passed."""
    import twag.cli.analyze as analyze_mod
    import twag.fetcher as fetcher_mod
    import twag.processor as processor_mod

    row = _sample_row(processed_at="2026-02-05T14:00:00+00:00")

    def _should_not_run(**kwargs):
        raise AssertionError("process_unprocessed should not run without --reprocess")

    monkeypatch.setattr(analyze_mod, "init_db", lambda: None)
    monkeypatch.setattr(analyze_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(analyze_mod, "get_tweet_by_id", lambda _conn, _tweet_id: row)
    monkeypatch.setattr(fetcher_mod, "read_tweet", lambda _status: _sample_tweet())
    monkeypatch.setattr(processor_mod, "store_fetched_tweets", lambda tweets, **kwargs: (len(tweets), 0))
    monkeypatch.setattr(processor_mod, "process_unprocessed", _should_not_run)

    runner = CliRunner()
    result = runner.invoke(cli, ["analyze", "2019488673935552978"])

    assert result.exit_code == 0
    assert "Status already processed; using existing analysis" in result.output


def test_analyze_status_reprocess_forces_refresh(monkeypatch):
    """--reprocess should force article/enrichment refresh path."""
    import twag.cli.analyze as analyze_mod
    import twag.fetcher as fetcher_mod
    import twag.processor as processor_mod

    calls = {"force_refresh": None}
    row = _sample_row(processed_at="2026-02-05T14:00:00+00:00")

    monkeypatch.setattr(analyze_mod, "init_db", lambda: None)
    monkeypatch.setattr(analyze_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(analyze_mod, "get_tweet_by_id", lambda _conn, _tweet_id: row)
    monkeypatch.setattr(fetcher_mod, "read_tweet", lambda _status: _sample_tweet())
    monkeypatch.setattr(processor_mod, "store_fetched_tweets", lambda tweets, **kwargs: (len(tweets), 0))
    monkeypatch.setattr(
        processor_mod,
        "process_unprocessed",
        lambda **kwargs: calls.__setitem__("force_refresh", kwargs.get("force_refresh")) or [],
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["analyze", "2019488673935552978", "--reprocess"])

    assert result.exit_code == 0
    assert calls["force_refresh"] is True


def test_analyze_status_not_found(monkeypatch):
    """Analyze should fail clearly when bird cannot read the status."""
    import twag.cli.analyze as analyze_mod
    import twag.fetcher as fetcher_mod

    monkeypatch.setattr(analyze_mod, "init_db", lambda: None)
    monkeypatch.setattr(fetcher_mod, "read_tweet", lambda _status: None)

    runner = CliRunner()
    result = runner.invoke(cli, ["analyze", "999"])

    assert result.exit_code == 1
    assert "Status not found or unreadable: 999" in result.output


def test_analyze_status_stores_thread_and_reply_context(monkeypatch):
    """Requested context should be stored while processing remains target-only."""
    import twag.cli.analyze as analyze_mod
    import twag.fetcher as fetcher_mod
    import twag.processor as processor_mod

    row = _sample_row(processed_at=None)
    target = _sample_tweet()
    reply = _sample_reply()
    stored_ids: list[str] = []
    processed_rows: list[dict] = []
    fetch_calls: list[tuple[str, str, dict]] = []

    monkeypatch.setattr(analyze_mod, "init_db", lambda: None)
    monkeypatch.setattr(analyze_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(analyze_mod, "get_tweet_by_id", lambda _conn, _tweet_id: row)
    monkeypatch.setattr(fetcher_mod, "read_tweet", lambda _status: target)
    monkeypatch.setattr(
        fetcher_mod,
        "fetch_thread",
        lambda status, **kwargs: fetch_calls.append(("thread", status, kwargs)) or [target],
    )
    monkeypatch.setattr(
        fetcher_mod,
        "fetch_replies",
        lambda status, **kwargs: fetch_calls.append(("replies", status, kwargs)) or [reply],
    )

    def _fake_store(tweets, **kwargs):
        stored_ids.extend(tweet.id for tweet in tweets)
        return len(tweets), len(tweets)

    def _fake_process(**kwargs):
        processed_rows.extend(kwargs["rows"])
        return []

    monkeypatch.setattr(processor_mod, "store_fetched_tweets", _fake_store)
    monkeypatch.setattr(processor_mod, "process_unprocessed", _fake_process)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "analyze",
            "2019488673935552978",
            "--thread",
            "--replies",
            "--reply-depth",
            "2",
            "--max-reply-nodes",
            "25",
            "--max-pages",
            "5",
        ],
    )

    assert result.exit_code == 0
    assert stored_ids == ["2019488673935552978", "reply-1"]
    assert [r["id"] for r in processed_rows] == ["2019488673935552978"]
    assert fetch_calls == [
        ("thread", "2019488673935552978", {"all_pages": False, "max_pages": 5}),
        ("replies", "2019488673935552978", {"all_pages": False, "max_pages": 5}),
        ("replies", "reply-1", {"all_pages": False, "max_pages": 5}),
    ]


def test_context_reply_depth_filters_descendants_and_caps_total(monkeypatch):
    """Reply traversal is breadth-first, direct-child only, and globally capped."""
    import twag.cli.analyze as analyze_mod
    import twag.fetcher as fetcher_mod

    target = _sample_tweet()
    direct_one = _sample_reply("reply-1", target.id)
    direct_two = _sample_reply("reply-2", target.id)
    nested_one = _sample_reply("nested-1", direct_one.id)
    nested_two = _sample_reply("nested-2", direct_one.id)
    calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(fetcher_mod, "fetch_thread", lambda *_args, **_kwargs: [])

    replies_by_id = {
        target.id: [direct_one, nested_one, direct_two],
        direct_one.id: [nested_one, nested_two],
        direct_two.id: [],
    }

    def _fake_fetch_replies(status_id, **kwargs):
        calls.append((status_id, kwargs))
        return replies_by_id.get(status_id, [])

    monkeypatch.setattr(fetcher_mod, "fetch_replies", _fake_fetch_replies)

    context = analyze_mod._fetch_context_tweets(
        target.id,
        target,
        include_thread=False,
        include_replies=True,
        reply_depth=2,
        max_reply_nodes=3,
        max_pages=None,
    )

    assert [tweet.id for tweet in context] == [target.id, "reply-1", "reply-2", "nested-1"]
    assert calls == [
        (target.id, {"all_pages": True, "max_pages": None}),
        ("reply-1", {"all_pages": True, "max_pages": None}),
    ]


def test_context_max_reply_nodes_also_caps_empty_source_fetches(monkeypatch):
    """A large thread cannot create unbounded reply-source requests."""
    import twag.cli.analyze as analyze_mod
    import twag.fetcher as fetcher_mod

    target = _sample_tweet()
    thread_tweets = [target, _sample_reply("thread-2", target.id), _sample_reply("thread-3", "thread-2")]
    reply_sources: list[str] = []

    monkeypatch.setattr(fetcher_mod, "fetch_thread", lambda *_args, **_kwargs: thread_tweets)
    monkeypatch.setattr(
        fetcher_mod,
        "fetch_replies",
        lambda status_id, **_kwargs: reply_sources.append(status_id) or [],
    )

    context = analyze_mod._fetch_context_tweets(
        target.id,
        target,
        include_thread=True,
        include_replies=True,
        reply_depth=2,
        max_reply_nodes=2,
        max_pages=5,
    )

    assert [tweet.id for tweet in context] == [target.id, "thread-2", "thread-3"]
    assert reply_sources == [target.id, "thread-2"]


def test_analyze_context_failure_is_secret_safe_and_nonzero(monkeypatch):
    """Explicit context fetches fail closed without echoing bird credentials/errors."""
    import twag.cli.analyze as analyze_mod
    import twag.fetcher as fetcher_mod

    monkeypatch.setattr(analyze_mod, "init_db", lambda: None)
    monkeypatch.setattr(fetcher_mod, "read_tweet", lambda _status: _sample_tweet())
    monkeypatch.setattr(
        fetcher_mod,
        "fetch_thread",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("AUTH_TOKEN=top-secret")),
    )

    result = CliRunner().invoke(cli, ["analyze", _sample_tweet().id, "--thread"])

    assert result.exit_code == 1
    assert "bird could not fetch thread context" in result.output
    assert "top-secret" not in result.output


def test_analyze_context_bounds_are_validated():
    """Negative reply bounds and zero page caps are rejected by Click."""
    runner = CliRunner()

    depth = runner.invoke(cli, ["analyze", "123", "--reply-depth", "-1"])
    nodes = runner.invoke(cli, ["analyze", "123", "--max-reply-nodes", "-1"])
    pages = runner.invoke(cli, ["analyze", "123", "--max-pages", "0"])

    assert depth.exit_code == 2
    assert nodes.exit_code == 2
    assert pages.exit_code == 2


def test_print_status_analysis_wraps_and_labels_long_fields(monkeypatch, capsys):
    """Long article sections should render as wrapped labeled blocks, not pipe-delimited lines."""
    import twag.cli.analyze as cli_mod

    row = _sample_row(processed_at="2026-02-05T14:00:00+00:00")
    row["summary"] = (
        "Deep dive into Google's record $180B 2026 capex guidance and why demand visibility from cloud "
        "and ads likely keeps ROI above the prior-cycle infrastructure baseline."
    )
    row["article_primary_points_json"] = json.dumps(
        [
            {
                "point": "Google's $180B capex plan is historically unprecedented at single-company scale.",
                "reasoning": "Magnitude rivals peak dotcom telecom buildout on an inflation-adjusted basis.",
                "evidence": "Compares to Apollo and Interstate totals while staying self-funded by operations.",
            },
        ],
    )
    row["article_action_items_json"] = json.dumps(
        [
            {
                "action": "Monitor GCP growth and backlog for demand durability.",
                "trigger": "Cloud growth decelerates below 30% or backlog growth stalls for two prints.",
                "horizon": "medium_term",
                "confidence": 0.7,
                "tickers": ["GOOGL", "MSFT", "AMZN"],
            },
        ],
    )
    monkeypatch.setattr(cli_mod, "_analysis_wrap_width", lambda: 72)

    cli_mod._print_status_analysis(row)
    output = capsys.readouterr().out

    assert "Primary Points:" in output
    assert "1. Google's $180B capex plan is historically unprecedented at" in output
    assert "single-company scale." in output
    assert "Why: Magnitude rivals peak dotcom telecom buildout on an" in output
    assert "inflation-adjusted basis." in output
    assert "Evidence: Compares to Apollo and Interstate totals while staying" in output
    assert "self-funded by operations." in output
    assert "Actionable Items:" in output
    assert "Trigger: Cloud growth decelerates below 30% or backlog growth stalls" in output
    assert "for two prints." in output
    assert "Horizon: medium term" in output
    assert "Confidence: 0.7" in output
    assert "Tickers: GOOGL, MSFT, AMZN" in output
    assert " | " not in output


def test_print_status_analysis_skips_invalid_points_and_actions(capsys):
    """Malformed point/action rows should be ignored without empty numbering output."""
    import twag.cli.analyze as cli_mod

    row = _sample_row(processed_at="2026-02-05T14:00:00+00:00")
    row["article_primary_points_json"] = json.dumps(
        [
            {"point": "", "reasoning": "missing main point", "evidence": "ignored"},
            {"reasoning": "non-point dict"},
        ],
    )
    row["article_action_items_json"] = json.dumps(
        [
            {"action": "", "trigger": "missing action"},
            {"trigger": "action key missing"},
        ],
    )

    cli_mod._print_status_analysis(row)
    output = capsys.readouterr().out

    assert "Primary Points:" not in output
    assert "Actionable Items:" not in output
