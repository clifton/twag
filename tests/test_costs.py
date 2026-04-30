"""Tests for twag.costs and the `twag costs` CLI."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch

from click.testing import CliRunner

from twag import metrics
from twag.cli import cli
from twag.cli.costs_cmd import _build_snapshot_from_db
from twag.costs import (
    Component,
    default_pricing_path,
    derive_model_from_label,
    estimate_costs,
    load_pricing_overrides,
    lookup_rate,
    total_usd,
)
from twag.metrics import MetricsCollector, ensure_metrics_table


def setup_function():
    metrics.reset()


# ── Pricing lookup ──────────────────────────────────────────────────────


def test_lookup_rate_exact_match():
    rate = lookup_rate("anthropic", "claude-opus-4-7")
    assert rate == (15.00, 75.00)


def test_lookup_rate_substring_match():
    # "gemini-3-flash-preview" is not in the table directly, but "gemini-3-flash" is
    rate = lookup_rate("gemini", "gemini-3-flash-preview")
    assert rate == (0.30, 2.50)


def test_lookup_rate_longest_substring_wins():
    # "gemini-2.5-pro-something" should pick "gemini-2.5-pro" (1.25, 10.0), not "gemini" (0.30, 2.50)
    rate = lookup_rate("gemini", "gemini-2.5-pro-something")
    assert rate == (1.25, 10.00)


def test_lookup_rate_unknown_model():
    rate = lookup_rate("openai", "gpt-7")
    assert rate is None


def test_lookup_rate_with_override():
    override = {("anthropic", "claude-experimental"): (1.0, 2.0)}
    rate = lookup_rate("anthropic", "claude-experimental", pricing=override)
    assert rate == (1.0, 2.0)


# ── derive_model_from_label ─────────────────────────────────────────────


def test_derive_model_from_label_no_labels():
    provider, model = derive_model_from_label("scorer.gemini.input_tokens")
    assert provider == "gemini"
    assert model is None


def test_derive_model_from_label_with_model():
    provider, model = derive_model_from_label("scorer.anthropic.output_tokens{model=claude-opus-4-7}")
    assert provider == "anthropic"
    assert model == "claude-opus-4-7"


def test_derive_model_from_label_multiple_labels():
    provider, model = derive_model_from_label("scorer.gemini.input_tokens{model=gemini-3-flash,role=triage}")
    assert provider == "gemini"
    assert model == "gemini-3-flash"


# ── estimate_costs ──────────────────────────────────────────────────────


def test_estimate_synthetic_snapshot_both_providers():
    snapshot = {
        "counters": {
            "scorer.gemini.calls": 10,
            "scorer.gemini.input_tokens": 100_000,
            "scorer.gemini.output_tokens": 20_000,
            "scorer.anthropic.calls": 5,
            "scorer.anthropic.input_tokens": 50_000,
            "scorer.anthropic.output_tokens": 10_000,
        },
        "histograms": {},
    }
    components = estimate_costs(
        snapshot,
        configured_models={"triage": "gemini-3-flash-preview", "enrichment": "claude-opus-4-7"},
    )
    by_name = {c.name: c for c in components}

    assert "scorer:gemini" in by_name
    # gemini-3-flash rates: (0.30, 2.50). 100k * 0.30/1M + 20k * 2.50/1M = 0.03 + 0.05 = 0.08
    assert abs(by_name["scorer:gemini"].usd_estimate - 0.08) < 1e-6

    assert "scorer:anthropic" in by_name
    # claude-opus-4-7 rates: (15, 75). 50k * 15/1M + 10k * 75/1M = 0.75 + 0.75 = 1.50
    assert abs(by_name["scorer:anthropic"].usd_estimate - 1.50) < 1e-6


def test_estimate_unknown_model_returns_zero_with_note():
    snapshot = {
        "counters": {
            "scorer.gemini.input_tokens{model=mystery-model-xyz}": 1_000_000,
            "scorer.gemini.output_tokens{model=mystery-model-xyz}": 1_000_000,
        },
        "histograms": {},
    }
    components = estimate_costs(snapshot, configured_models={})
    by_name = {c.name: c for c in components}
    assert by_name["scorer:gemini"].usd_estimate == 0.0
    assert "no pricing entry" in by_name["scorer:gemini"].notes


def test_estimate_falls_back_to_configured_model():
    snapshot = {
        "counters": {
            "scorer.gemini.input_tokens": 1_000_000,
            "scorer.gemini.output_tokens": 1_000_000,
        },
        "histograms": {},
    }
    components = estimate_costs(
        snapshot,
        configured_models={"triage": "gemini-3-flash-preview", "enrichment": "claude-opus-4-7"},
    )
    by_name = {c.name: c for c in components}
    # Should use gemini-3-flash rates: input=0.30, output=2.50 per 1M
    expected = (1_000_000 * 0.30 + 1_000_000 * 2.50) / 1_000_000
    assert abs(by_name["scorer:gemini"].usd_estimate - expected) < 1e-6


def test_estimate_no_scorer_activity_still_emits_components():
    snapshot = {"counters": {}, "histograms": {}}
    components = estimate_costs(snapshot)
    names = {c.name for c in components}
    assert "scorer" in names
    assert "fetcher" in names
    assert "pipeline" in names
    assert "web" in names


def test_estimate_non_llm_components_have_notes():
    snapshot = {
        "counters": {
            "fetcher.bird.calls": 12,
            "web.requests": 99,
        },
        "histograms": {
            "pipeline.batch_seconds": {"count": 3, "total": 12.5, "mean": 4.16, "min": 1, "max": 7, "p50": 4, "p99": 7},
        },
    }
    components = estimate_costs(snapshot)
    by_name = {c.name: c for c in components}
    assert by_name["fetcher"].usd_estimate == 0.0
    assert by_name["fetcher"].breakdown["calls"] == 12
    assert "bird" in by_name["fetcher"].notes
    assert by_name["web"].breakdown["requests"] == 99
    assert by_name["pipeline"].breakdown["compute_seconds"] == 12.5


# ── Pricing override file ───────────────────────────────────────────────


def test_pricing_override_file_dict_format(tmp_path):
    path = tmp_path / "pricing.json"
    path.write_text(
        json.dumps({"anthropic": {"claude-opus-4-7": {"input_per_million_usd": 1.0, "output_per_million_usd": 2.0}}}),
    )
    overrides = load_pricing_overrides(path)
    assert overrides[("anthropic", "claude-opus-4-7")] == (1.0, 2.0)


def test_pricing_override_file_list_format(tmp_path):
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps({"gemini": {"gemini-3-pro": [9.0, 18.0]}}))
    overrides = load_pricing_overrides(path)
    assert overrides[("gemini", "gemini-3-pro")] == (9.0, 18.0)


def test_pricing_override_file_missing_returns_empty(tmp_path):
    overrides = load_pricing_overrides(tmp_path / "does_not_exist.json")
    assert overrides == {}


def test_pricing_override_changes_estimate():
    snapshot = {
        "counters": {
            "scorer.anthropic.input_tokens{model=claude-opus-4-7}": 1_000_000,
            "scorer.anthropic.output_tokens{model=claude-opus-4-7}": 0,
        },
        "histograms": {},
    }
    override = {("anthropic", "claude-opus-4-7"): (1.0, 0.0)}
    components = estimate_costs(snapshot, pricing=override)
    by_name = {c.name: c for c in components}
    # 1M tokens * 1.0/M = 1.00
    assert abs(by_name["scorer:anthropic"].usd_estimate - 1.0) < 1e-6


# ── total_usd ───────────────────────────────────────────────────────────


def test_total_usd_sums_components():
    components = [
        Component(name="a", usd_estimate=1.5),
        Component(name="b", usd_estimate=2.25),
        Component(name="c", usd_estimate=0.0),
    ]
    assert total_usd(components) == 3.75


# ── CLI ─────────────────────────────────────────────────────────────────


def test_cli_costs_json_live():
    """Live snapshot path: skips the SQLite query entirely."""
    metrics.reset()
    metrics.counter("scorer.gemini.input_tokens", value=1_000)
    metrics.counter("scorer.gemini.output_tokens", value=500)

    runner = CliRunner()
    with patch("twag.cli.costs_cmd.load_config", return_value={"llm": {"triage_model": "gemini-3-flash-preview"}}):
        result = runner.invoke(cli, ["costs", "--since", "live", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "components" in payload
    assert "total_usd" in payload
    assert payload["window"] == "live"

    names = {c["name"] for c in payload["components"]}
    assert "scorer:gemini" in names
    assert "fetcher" in names
    assert "pipeline" in names
    assert "web" in names

    gemini = next(c for c in payload["components"] if c["name"] == "scorer:gemini")
    assert "input_tokens" in gemini["breakdown"]
    assert "output_tokens" in gemini["breakdown"]


def test_cli_costs_table_renders():
    metrics.reset()
    metrics.counter("scorer.anthropic.input_tokens", value=1_000)
    metrics.counter("scorer.anthropic.output_tokens", value=500)

    runner = CliRunner()
    with patch("twag.cli.costs_cmd.load_config", return_value={"llm": {"enrichment_model": "claude-opus-4-7"}}):
        # Force a wide terminal so Rich doesn't truncate the component name.
        with patch.dict("os.environ", {"COLUMNS": "200"}):
            result = runner.invoke(cli, ["costs", "--since", "live"])

    assert result.exit_code == 0, result.output
    assert "Estimated costs" in result.output
    # The Rich table renders provider names; allow either full or truncated forms.
    assert "scorer:anthropic" in result.output or "anthropic" in result.output
    assert "TOTAL" in result.output


def test_cli_costs_pricing_file_option(tmp_path):
    metrics.reset()
    metrics.counter("scorer.anthropic.input_tokens", value=1_000_000)
    metrics.counter("scorer.anthropic.output_tokens", value=0)

    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text(
        json.dumps({"anthropic": {"claude-opus-4-7": {"input_per_million_usd": 2.0, "output_per_million_usd": 0.0}}}),
    )

    runner = CliRunner()
    with patch("twag.cli.costs_cmd.load_config", return_value={"llm": {"enrichment_model": "claude-opus-4-7"}}):
        result = runner.invoke(cli, ["costs", "--since", "live", "--json", "--pricing-file", str(pricing_file)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    anthropic = next(c for c in payload["components"] if c["name"] == "scorer:anthropic")
    # 1M tokens * 2.0/1M = 2.0
    assert abs(anthropic["usd_estimate"] - 2.0) < 1e-6


# ── Persisted counters: delta semantics across process lifetimes ─────────


def test_flush_to_db_writes_delta_not_cumulative():
    """Each flush should record only the delta since the previous flush.

    Cumulative-snapshot rows would force a window-aggregator to choose between
    SUM (double-counts within one process) or MAX (loses cross-process spend).
    Storing deltas lets the window query be a simple SUM.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_metrics_table(conn)

    m = MetricsCollector()
    m.inc("scorer.gemini.input_tokens", 100)
    m.flush_to_db(conn)

    m.inc("scorer.gemini.input_tokens", 50)
    m.flush_to_db(conn)

    rows = conn.execute(
        "SELECT value FROM metrics WHERE name = 'scorer.gemini.input_tokens' AND type = 'counter'",
    ).fetchall()
    values = [r["value"] for r in rows]
    assert values == [100, 50], f"expected per-flush deltas, got {values}"
    # Sum across rows should equal current cumulative value.
    assert sum(values) == m.counter_value("scorer.gemini.input_tokens") == 150


def test_flush_to_db_skips_unchanged_counters():
    """A flush with no counter activity should not insert duplicate rows."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_metrics_table(conn)

    m = MetricsCollector()
    m.inc("scorer.anthropic.input_tokens", 25)
    first = m.flush_to_db(conn)
    second = m.flush_to_db(conn)
    assert first == 1
    assert second == 0


def test_flush_summed_across_two_collectors_recovers_total():
    """Cross-process scenario: two independent collectors that each flush.

    The fix from review iteration 1: process A flushes 100 + 50, process B
    starts fresh and flushes 30 — the window total must be 180, not 150 (the
    old MAX-based reconstruction returned 150).
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_metrics_table(conn)

    a = MetricsCollector()
    a.inc("scorer.gemini.input_tokens", 100)
    a.flush_to_db(conn)
    a.inc("scorer.gemini.input_tokens", 50)
    a.flush_to_db(conn)

    b = MetricsCollector()
    b.inc("scorer.gemini.input_tokens", 30)
    b.flush_to_db(conn)

    total = conn.execute(
        "SELECT SUM(value) AS s FROM metrics WHERE name = 'scorer.gemini.input_tokens' AND type = 'counter'",
    ).fetchone()["s"]
    assert total == 180


def test_build_snapshot_from_db_sums_cross_process_deltas(monkeypatch):
    """End-to-end: the CLI window-aggregator returns the true cross-process sum."""
    db_file = sqlite3.connect(":memory:")
    db_file.row_factory = sqlite3.Row
    ensure_metrics_table(db_file)

    a = MetricsCollector()
    a.inc("scorer.gemini.input_tokens{model=gemini-3-flash-preview}", 100)
    a.flush_to_db(db_file)
    a.inc("scorer.gemini.input_tokens{model=gemini-3-flash-preview}", 50)
    a.flush_to_db(db_file)
    b = MetricsCollector()
    b.inc("scorer.gemini.input_tokens{model=gemini-3-flash-preview}", 30)
    b.flush_to_db(db_file)

    # Patch the connection helper so _build_snapshot_from_db sees our in-memory DB.
    from contextlib import contextmanager

    @contextmanager
    def _conn(**_kw):
        yield db_file

    monkeypatch.setattr("twag.cli.costs_cmd.get_connection", _conn)

    from datetime import timedelta

    snapshot = _build_snapshot_from_db(timedelta(days=1))
    assert snapshot["counters"]["scorer.gemini.input_tokens{model=gemini-3-flash-preview}"] == 180


# ── XDG path ────────────────────────────────────────────────────────────


def test_default_pricing_path_is_xdg(monkeypatch, tmp_path):
    """Default override file should live under XDG_CONFIG_HOME/twag/, not ~/.twag/."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    expected = tmp_path / "twag" / "pricing.json"
    assert default_pricing_path() == expected


# ── Labeled counters from llm_client are correctly attributed ───────────


def test_labeled_counters_per_model_are_priced_independently():
    """Two Gemini models in the same provider bucket should each price using
    their own row in PRICING -- not collapse into a single configured default.
    """
    snapshot = {
        "counters": {
            # 1M input tokens on gemini-3-flash → 0.30 USD
            "scorer.gemini.input_tokens{model=gemini-3-flash-preview}": 1_000_000,
            "scorer.gemini.output_tokens{model=gemini-3-flash-preview}": 0,
            # 1M input tokens on gemini-3-pro → 3.50 USD
            "scorer.gemini.input_tokens{model=gemini-3-pro-preview}": 1_000_000,
            "scorer.gemini.output_tokens{model=gemini-3-pro-preview}": 0,
        },
        "histograms": {},
    }
    components = estimate_costs(snapshot, configured_models={})
    by_name = {c.name: c for c in components}
    gemini = by_name["scorer:gemini"]
    # 0.30 + 3.50 = 3.80
    assert abs(gemini.usd_estimate - 3.80) < 1e-6
    # And both models appear in the per-model breakdown
    assert "gemini-3-flash-preview" in gemini.breakdown["models"]
    assert "gemini-3-pro-preview" in gemini.breakdown["models"]
    assert abs(gemini.breakdown["models"]["gemini-3-flash-preview"]["usd_estimate"] - 0.30) < 1e-6
    assert abs(gemini.breakdown["models"]["gemini-3-pro-preview"]["usd_estimate"] - 3.50) < 1e-6
