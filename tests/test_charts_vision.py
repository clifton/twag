"""Contract tests for routing twag vision through the local charts service."""

from __future__ import annotations

import json
import subprocess

import pytest

import twag.processor.triage as triage_mod
import twag.scorer.charts_client as charts_client
import twag.scorer.scoring as scoring_mod
from twag.db import get_connection, init_db
from twag.metrics import get_collector
from twag.scorer import MediaAnalysisResult
from twag.scorer.charts_client import (
    ChartsAnalysis,
    ChartsAnalysisError,
    ChartsProcessResult,
    ChartsUnavailableError,
)


def _charts_payload(*, kind: str = "chart", status: str = "active", cached: bool = False) -> dict:
    chart_id = "a" * 64
    return {
        "id": chart_id,
        "ext": "jpg",
        "kind": kind,
        "status": status,
        "tag_status": "tagged",
        "title": "US real yields",
        "transcript": "Line chart of the US 10-year real yield.",
        "insight": "Real yields rose through the latest observation.",
        "caption": "Real yields are moving",
        "tags": {
            "tickers": ["TIP"],
            "countries": ["US"],
            "asset_classes": ["rates"],
            "fx_pairs": [],
            "indices": [],
            "concepts": ["real yields"],
            "themes": ["higher-for-longer"],
        },
        "cdn_url": None if status == "rejected" else f"https://charts.example/c/{chart_id}.jpg",
        "cached": cached,
    }


def _charts_analysis(**overrides) -> ChartsAnalysis:
    return charts_client._validate_success({**_charts_payload(), **overrides})


def _charts_config() -> dict:
    return {
        "llm": {
            "vision_model": "gemini-fallback",
            "vision_provider": "charts",
            "charts_executable": "/usr/local/bin/charts",
            "charts_deadline_seconds": 90,
        },
    }


def test_charts_runner_uses_argument_array_and_maps_contract() -> None:
    invocations: list[tuple[list[str], float]] = []

    def runner(args: list[str], deadline: float) -> ChartsProcessResult:
        invocations.append((args, deadline))
        return ChartsProcessResult(0, json.dumps(_charts_payload(cached=True)), "")

    result = charts_client.analyze_with_charts(
        "https://example.com/chart.jpg",
        caption="tweet text",
        executable="/opt/bin/charts",
        deadline_seconds=90,
        runner=runner,
    )

    assert invocations == [
        (
            [
                "/opt/bin/charts",
                "analyze",
                "https://example.com/chart.jpg",
                "--source",
                "twitter",
                "--caption",
                "tweet text",
                "--json",
            ],
            90,
        ),
    ]
    mapped = scoring_mod._media_result_from_charts(result)
    assert mapped.kind == "chart"
    assert mapped.prose_text == "Line chart of the US 10-year real yield."
    assert mapped.prose_summary == "Real yields rose through the latest observation."
    assert mapped.short_description == mapped.prose_summary
    assert mapped.chart["tickers"] == ["TIP"]
    assert mapped.chart["tags"]["countries"] == ["US"]
    assert mapped.charts_id == "a" * 64
    assert mapped.cdn_url == f"https://charts.example/c/{'a' * 64}.jpg"
    assert mapped.charts_cached is True


def test_rejected_charts_result_is_accepted_without_fallback(monkeypatch) -> None:
    rejected = _charts_analysis(kind="photo", status="rejected", cdn_url=None)
    monkeypatch.setattr(scoring_mod, "load_config", _charts_config)
    monkeypatch.setattr(scoring_mod, "analyze_with_charts", lambda *args, **kwargs: rejected)
    monkeypatch.setattr(
        scoring_mod,
        "_call_llm_vision_once",
        lambda *args, **kwargs: pytest.fail("rejected charts result must not fallback"),
    )
    usage: list[dict] = []

    result = scoring_mod.analyze_media(
        "https://example.com/photo.jpg",
        caption="conference photo",
        usage_recorder=usage.append,
    )

    assert result.kind == "photo"
    assert result.charts_id == rejected.id
    assert result.cdn_url is None
    assert len(usage) == 1
    assert usage[0]["provider"] == "charts"
    assert usage[0]["model"] == "charts"
    assert usage[0]["success"] is True
    assert usage[0]["metadata"]["status"] == "rejected"


def test_charts_call_logs_zero_cost_usage_row(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))
    init_db(tmp_path / "twag.db")
    monkeypatch.setattr(scoring_mod, "load_config", _charts_config)
    monkeypatch.setattr(scoring_mod, "analyze_with_charts", lambda *args, **kwargs: _charts_analysis())
    monkeypatch.setattr(
        scoring_mod,
        "_call_llm_vision_once",
        lambda *args, **kwargs: pytest.fail("successful charts result must not fallback"),
    )

    scoring_mod.analyze_media(
        "https://example.com/chart.jpg",
        caption="caption for charts",
    )

    with get_connection(tmp_path / "twag.db", readonly=True) as conn:
        row = conn.execute(
            """
            SELECT component, provider, model, is_vision, estimated_cost_usd,
                   success, metadata_json
            FROM llm_usage
            """,
        ).fetchone()
    assert row["component"] == "vision"
    assert row["provider"] == "charts"
    assert row["model"] == "charts"
    assert row["is_vision"] == 1
    assert row["estimated_cost_usd"] == 0
    assert row["success"] == 1
    assert json.loads(row["metadata_json"])["charts_id"] == "a" * 64


def test_structured_charts_failure_never_falls_back(monkeypatch) -> None:
    error = ChartsAnalysisError(
        "Gemini HTTP 503",
        {"error": "Gemini HTTP 503", "id": "b" * 64, "tag_status": "failed", "tag_attempts": 1},
    )
    monkeypatch.setattr(scoring_mod, "load_config", _charts_config)
    monkeypatch.setattr(
        scoring_mod,
        "analyze_with_charts",
        lambda *args, **kwargs: (_ for _ in ()).throw(error),
    )
    monkeypatch.setattr(
        scoring_mod,
        "_call_llm_vision_once",
        lambda *args, **kwargs: pytest.fail("structured charts failure must not fallback"),
    )
    usage: list[dict] = []

    with pytest.raises(ChartsAnalysisError, match="Gemini HTTP 503"):
        scoring_mod.analyze_media(
            "https://example.com/failing.jpg",
            caption="failing chart",
            usage_recorder=usage.append,
        )

    assert len(usage) == 1
    assert usage[0]["provider"] == "charts"
    assert usage[0]["success"] is False
    assert usage[0]["metadata"]["failure"] == "structured"


def test_unavailable_charts_falls_back_to_exactly_one_direct_call(monkeypatch) -> None:
    monkeypatch.setattr(scoring_mod, "load_config", _charts_config)
    monkeypatch.setattr(
        scoring_mod,
        "analyze_with_charts",
        lambda *args, **kwargs: (_ for _ in ()).throw(ChartsUnavailableError("spawn_failure", "missing")),
    )
    calls: list[tuple] = []

    def direct_call(*args, **kwargs):
        calls.append((args, kwargs))
        return json.dumps(
            {
                "kind": "chart",
                "short_description": "Fallback chart",
                "prose_text": "Fallback transcript",
                "prose_summary": "Fallback insight",
                "chart": {},
                "table": {},
            },
        )

    monkeypatch.setattr(scoring_mod, "_call_llm_vision_once", direct_call)
    get_collector().reset()
    usage: list[dict] = []

    result = scoring_mod.analyze_media(
        "https://example.com/fallback.jpg",
        caption="fallback tweet",
        usage_recorder=usage.append,
    )

    assert len(calls) == 1
    assert calls[0][0][:3] == ("gemini", "gemini-fallback", "https://example.com/fallback.jpg")
    assert result.analysis_provider == "gemini"
    assert result.analysis_model == "gemini-fallback"
    assert result.charts_id is None
    assert len(usage) == 1
    assert usage[0]["provider"] == "charts"
    assert usage[0]["metadata"]["unavailable_reason"] == "spawn_failure"
    assert get_collector().counter_value("scorer.charts.unavailable.spawn_failure") == 1


def test_invalid_contract_is_unavailable_but_structured_nonzero_is_not() -> None:
    with pytest.raises(ChartsUnavailableError) as invalid:
        charts_client.analyze_with_charts(
            "image.jpg",
            caption="caption",
            runner=lambda _args, _deadline: ChartsProcessResult(0, '{"id": "short"}', ""),
        )
    assert invalid.value.reason == "invalid_contract"

    with pytest.raises(ChartsAnalysisError) as structured:
        charts_client.analyze_with_charts(
            "image.jpg",
            caption="caption",
            runner=lambda _args, _deadline: ChartsProcessResult(
                1,
                "",
                json.dumps({"error": "image download failed: HTTP 404"}),
            ),
        )
    assert "HTTP 404" in str(structured.value)


def test_deadline_kills_charts_child() -> None:
    class FakeProcess:
        returncode = None

        def __init__(self):
            self.killed = False
            self.communicate_calls = 0

        def communicate(self, timeout=None):
            self.communicate_calls += 1
            if self.communicate_calls == 1:
                raise subprocess.TimeoutExpired(["charts"], timeout)
            self.returncode = -9
            return "", ""

        def kill(self):
            self.killed = True

    process = FakeProcess()
    popen_calls: list[tuple[list[str], dict]] = []

    def popen_factory(args, **kwargs):
        popen_calls.append((args, kwargs))
        return process

    with pytest.raises(ChartsUnavailableError) as timeout:
        charts_client.run_charts_process(
            ["charts", "analyze", "image.jpg"],
            90,
            popen_factory=popen_factory,
        )

    assert timeout.value.reason == "deadline"
    assert process.killed is True
    assert process.communicate_calls == 2
    assert popen_calls[0][1]["text"] is True


def test_charts_l1_cache_hit_keeps_id_and_skips_child(monkeypatch) -> None:
    cached = {
        "kind": "chart",
        "short_description": "Cached chart",
        "prose_text": "Cached transcript",
        "prose_summary": "Cached insight",
        "chart": {"tickers": ["TIP"]},
        "table": {},
        "charts_id": "c" * 64,
        "cdn_url": f"https://charts.example/c/{'c' * 64}.jpg",
        "charts_cached": False,
    }
    monkeypatch.setattr(triage_mod, "load_config", _charts_config)

    def get_cached(url, *, provider, model):
        assert provider == "charts"
        assert model == "charts"
        return cached

    monkeypatch.setattr(triage_mod, "get_cached_media_analysis", get_cached)
    monkeypatch.setattr(triage_mod, "increment_media_analysis_cache_hit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        triage_mod,
        "analyze_media",
        lambda *args, **kwargs: pytest.fail("charts child must not spawn on L1 hit"),
    )

    items, updated = triage_mod._analyze_media_items(
        [{"url": "https://example.com/cached.jpg"}],
        caption="tweet caption",
    )

    assert updated is True
    assert items[0]["charts_id"] == "c" * 64
    assert items[0]["cdn_url"].endswith(".jpg")


def test_fallback_result_is_not_cached_under_charts_key(monkeypatch) -> None:
    monkeypatch.setattr(triage_mod, "load_config", _charts_config)
    monkeypatch.setattr(triage_mod, "get_cached_media_analysis", lambda *args, **kwargs: None)
    recorded: list[tuple[str | None, str | None]] = []
    monkeypatch.setattr(
        triage_mod,
        "record_media_analysis",
        lambda _url, *, provider, model, result: recorded.append((provider, model)),
    )
    monkeypatch.setattr(
        triage_mod,
        "analyze_media",
        lambda *args, **kwargs: MediaAnalysisResult(
            kind="chart",
            short_description="fallback",
            prose_text="",
            prose_summary="",
            analysis_provider="gemini",
            analysis_model="gemini-fallback",
        ),
    )

    triage_mod._analyze_media_items([{"url": "https://example.com/fallback.jpg"}])

    assert recorded == [("gemini", "gemini-fallback")]


def test_fresh_charts_result_is_cached_under_charts_key(monkeypatch) -> None:
    monkeypatch.setattr(triage_mod, "load_config", _charts_config)
    monkeypatch.setattr(triage_mod, "get_cached_media_analysis", lambda *args, **kwargs: None)
    recorded: list[tuple[str | None, str | None, str | None]] = []
    monkeypatch.setattr(
        triage_mod,
        "record_media_analysis",
        lambda _url, *, provider, model, result: recorded.append((provider, model, result["charts_id"])),
    )

    def analyze(_url, **kwargs):
        assert kwargs["caption"] == "tweet caption"
        return MediaAnalysisResult(
            kind="chart",
            short_description="charts result",
            prose_text="",
            prose_summary="",
            charts_id="d" * 64,
            cdn_url=f"https://charts.example/c/{'d' * 64}.jpg",
            charts_cached=False,
            analysis_provider="charts",
            analysis_model="charts",
        )

    monkeypatch.setattr(triage_mod, "analyze_media", analyze)

    triage_mod._analyze_media_items(
        [{"url": "https://example.com/fresh.jpg"}],
        caption="tweet caption",
    )

    assert recorded == [("charts", "charts", "d" * 64)]
