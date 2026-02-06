"""CLI tests for one-shot status analysis command."""

import json
from contextlib import contextmanager

from click.testing import CliRunner

from twag.cli import cli
from twag.fetcher import Tweet


def _sample_tweet() -> Tweet:
    return Tweet(
        id="2019488673935552978",
        author_handle="undrvalue",
        author_name="market participant",
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


@contextmanager
def _fake_connection(readonly=False):
    yield object()


def _sample_row(processed_at: str | None = None) -> dict:
    return {
        "id": "2019488673935552978",
        "author_handle": "undrvalue",
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
                }
            ]
        ),
        "article_action_items_json": json.dumps(
            [
                {
                    "action": "Track hyperscaler ROI disclosures",
                    "trigger": "If capex growth outpaces revenue growth for 2+ quarters",
                    "horizon": "2-4 quarters",
                    "confidence": "medium",
                    "tickers": ["GOOGL", "MSFT"],
                }
            ]
        ),
        "article_top_visual_json": json.dumps(
            {
                "url": "https://pbs.twimg.com/media/HAXmiH6acAEiywu.jpg",
                "kind": "chart",
                "why_important": "Most relevant quantitative visual supporting the thesis.",
                "key_takeaway": "2026 capex bar is the largest in the series.",
            }
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
            ]
        ),
        "processed_at": processed_at,
    }


def test_analyze_status_success(monkeypatch):
    """Analyze should fetch, process, and print structured article sections."""
    import twag.cli as cli_mod
    import twag.fetcher as fetcher_mod
    import twag.processor as processor_mod

    process_calls = {"count": 0, "force_refresh": None}
    row = _sample_row(processed_at=None)

    monkeypatch.setattr(cli_mod, "init_db", lambda: None)
    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(fetcher_mod, "read_tweet", lambda _status: _sample_tweet())
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
    monkeypatch.setattr(cli_mod, "get_tweet_by_id", lambda _conn, _tweet_id: row)

    runner = CliRunner()
    result = runner.invoke(cli, ["analyze", "https://x.com/undrvalue/status/2019488673935552978"])

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
    import twag.cli as cli_mod
    import twag.fetcher as fetcher_mod
    import twag.processor as processor_mod

    row = _sample_row(processed_at="2026-02-05T14:00:00+00:00")

    def _should_not_run(**kwargs):
        raise AssertionError("process_unprocessed should not run without --reprocess")

    monkeypatch.setattr(cli_mod, "init_db", lambda: None)
    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_tweet_by_id", lambda _conn, _tweet_id: row)
    monkeypatch.setattr(fetcher_mod, "read_tweet", lambda _status: _sample_tweet())
    monkeypatch.setattr(processor_mod, "store_fetched_tweets", lambda tweets, **kwargs: (len(tweets), 0))
    monkeypatch.setattr(processor_mod, "process_unprocessed", _should_not_run)

    runner = CliRunner()
    result = runner.invoke(cli, ["analyze", "2019488673935552978"])

    assert result.exit_code == 0
    assert "Status already processed; using existing analysis" in result.output


def test_analyze_status_reprocess_forces_refresh(monkeypatch):
    """--reprocess should force article/enrichment refresh path."""
    import twag.cli as cli_mod
    import twag.fetcher as fetcher_mod
    import twag.processor as processor_mod

    calls = {"force_refresh": None}
    row = _sample_row(processed_at="2026-02-05T14:00:00+00:00")

    monkeypatch.setattr(cli_mod, "init_db", lambda: None)
    monkeypatch.setattr(cli_mod, "get_connection", _fake_connection)
    monkeypatch.setattr(cli_mod, "get_tweet_by_id", lambda _conn, _tweet_id: row)
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
    import twag.cli as cli_mod
    import twag.fetcher as fetcher_mod

    monkeypatch.setattr(cli_mod, "init_db", lambda: None)
    monkeypatch.setattr(fetcher_mod, "read_tweet", lambda _status: None)

    runner = CliRunner()
    result = runner.invoke(cli, ["analyze", "999"])

    assert result.exit_code == 1
    assert "Status not found or unreadable: 999" in result.output


def test_print_status_analysis_wraps_and_labels_long_fields(monkeypatch, capsys):
    """Long article sections should render as wrapped labeled blocks, not pipe-delimited lines."""
    import twag.cli as cli_mod

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
            }
        ]
    )
    row["article_action_items_json"] = json.dumps(
        [
            {
                "action": "Monitor GCP growth and backlog for demand durability.",
                "trigger": "Cloud growth decelerates below 30% or backlog growth stalls for two prints.",
                "horizon": "medium_term",
                "confidence": 0.7,
                "tickers": ["GOOGL", "MSFT", "AMZN"],
            }
        ]
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
    import twag.cli as cli_mod

    row = _sample_row(processed_at="2026-02-05T14:00:00+00:00")
    row["article_primary_points_json"] = json.dumps(
        [
            {"point": "", "reasoning": "missing main point", "evidence": "ignored"},
            {"reasoning": "non-point dict"},
        ]
    )
    row["article_action_items_json"] = json.dumps(
        [
            {"action": "", "trigger": "missing action"},
            {"trigger": "action key missing"},
        ]
    )

    cli_mod._print_status_analysis(row)
    output = capsys.readouterr().out

    assert "Primary Points:" not in output
    assert "Actionable Items:" not in output
