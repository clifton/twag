"""Tests for scripts/analyze_test_flakiness.py pure helpers.

Covers:
- JUnit XML parsing into TestOutcomes
- Cross-run aggregation and flaky classification
- Static smell regex detection (positives, negatives, exemptions)
- Markdown rendering basic shape

Kept pure so the analyzer itself does not become a flaky test.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "analyze_test_flakiness.py"


def _load_analyzer():
    """Load the analyzer script as a module without executing main()."""
    spec = importlib.util.spec_from_file_location("analyze_test_flakiness", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["analyze_test_flakiness"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def analyzer():
    return _load_analyzer()


# ---------------------------------------------------------------------------
# JUnit XML parsing
# ---------------------------------------------------------------------------

JUNIT_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="4" failures="1" errors="1" skipped="1">
    <testcase classname="tests.test_foo" name="test_pass" time="0.012" />
    <testcase classname="tests.test_foo" name="test_fail" time="0.005">
      <failure message="assert 1 == 2">long traceback here</failure>
    </testcase>
    <testcase classname="tests.test_bar.TestThing" name="test_error" time="0.001">
      <error message="ImportError: nope">trace</error>
    </testcase>
    <testcase classname="tests.test_baz" name="test_skip" time="0.0">
      <skipped message="needs network" />
    </testcase>
  </testsuite>
</testsuites>
"""


def test_parse_junit_xml_extracts_all_statuses(analyzer):
    outcomes = analyzer.parse_junit_xml(JUNIT_SAMPLE)
    assert len(outcomes) == 4
    by_id = {o.nodeid: o for o in outcomes}

    assert by_id["tests/test_foo.py::test_pass"].status == "passed"
    assert by_id["tests/test_foo.py::test_fail"].status == "failed"
    assert "assert 1 == 2" in by_id["tests/test_foo.py::test_fail"].message
    assert by_id["tests/test_bar.py::TestThing::test_error"].status == "error"
    assert by_id["tests/test_baz.py::test_skip"].status == "skipped"
    assert by_id["tests/test_foo.py::test_pass"].duration == pytest.approx(0.012)


def test_parse_junit_xml_handles_empty(analyzer):
    assert analyzer.parse_junit_xml("") == []


def test_parse_junit_xml_handles_single_suite_root(analyzer):
    # Some pytest versions emit <testsuite> at the root, not <testsuites>.
    xml = (
        '<testsuite name="pytest" tests="1">'
        '<testcase classname="tests.test_x" name="test_one" time="0.0" />'
        "</testsuite>"
    )
    outcomes = analyzer.parse_junit_xml(xml)
    assert len(outcomes) == 1
    assert outcomes[0].nodeid == "tests/test_x.py::test_one"
    assert outcomes[0].status == "passed"


# ---------------------------------------------------------------------------
# Aggregation and classification
# ---------------------------------------------------------------------------


def _make_run(analyzer, idx: int, statuses: dict[str, str]):
    return analyzer.RunResult(
        run_index=idx,
        seed=1000 + idx,
        outcomes=[analyzer.TestOutcome(nodeid=nid, status=st) for nid, st in statuses.items()],
        returncode=0,
    )


def test_aggregate_outcomes_collects_per_run_statuses(analyzer):
    runs = [
        _make_run(analyzer, 1, {"a::t": "passed", "b::t": "failed"}),
        _make_run(analyzer, 2, {"a::t": "passed", "b::t": "passed"}),
        _make_run(analyzer, 3, {"a::t": "passed"}),  # b::t missing
    ]
    agg = analyzer.aggregate_outcomes(runs)
    assert agg["a::t"] == ["passed", "passed", "passed"]
    assert agg["b::t"] == ["failed", "passed", "missing"]


def test_classify_flaky_flags_mixed_outcomes(analyzer):
    agg = {
        "always_pass::t": ["passed", "passed", "passed"],
        "always_fail::t": ["failed", "failed", "failed"],
        "flaky::t": ["passed", "failed", "passed"],
        "flaky_err::t": ["error", "passed", "passed"],
        "skipped_only::t": ["skipped", "skipped", "skipped"],
    }
    flaky = analyzer.classify_flaky(agg)
    nodeids = {f.nodeid for f in flaky}
    assert nodeids == {"flaky::t", "flaky_err::t"}

    by_id = {f.nodeid: f for f in flaky}
    assert by_id["flaky::t"].pass_count == 2
    assert by_id["flaky::t"].fail_count == 1
    assert by_id["flaky_err::t"].fail_count == 1


def test_classify_flaky_orders_by_failure_count_desc(analyzer):
    agg = {
        "low::t": ["passed", "passed", "failed"],
        "high::t": ["failed", "failed", "passed"],
        "mid::t": ["passed", "failed", "passed"],
    }
    flaky = analyzer.classify_flaky(agg)
    assert [f.nodeid for f in flaky] == ["high::t", "low::t", "mid::t"]


# ---------------------------------------------------------------------------
# Static smell detection
# ---------------------------------------------------------------------------


def test_scan_file_for_smells_detects_real_sleep(analyzer):
    content = "import time\n\ndef test_x():\n    time.sleep(1)\n"
    smells = analyzer.scan_file_for_smells(Path("tests/fake.py"), content)
    cats = {s.category for s in smells}
    assert "real_sleep" in cats


def test_scan_file_for_smells_exempts_async_sleep(analyzer):
    content = "async def test_x():\n    await asyncio.sleep(0)\n"
    smells = analyzer.scan_file_for_smells(Path("tests/fake.py"), content)
    cats = {s.category for s in smells}
    assert "real_sleep" not in cats


def test_scan_file_for_smells_detects_real_clock(analyzer):
    content = "from datetime import datetime\n\ndef test_x():\n    x = datetime.now()\n"
    smells = analyzer.scan_file_for_smells(Path("tests/fake.py"), content)
    cats = {s.category for s in smells}
    assert "real_clock_now" in cats


def test_scan_file_for_smells_exempts_clock_under_freezegun(analyzer):
    content = (
        "from freezegun import freeze_time\n\ndef test_x():\n    with freeze_time('2024-01-01'): x = datetime.now()\n"
    )
    smells = analyzer.scan_file_for_smells(Path("tests/fake.py"), content)
    cats = {s.category for s in smells}
    assert "real_clock_now" not in cats


def test_scan_file_for_smells_unseeded_random_when_no_seed(analyzer):
    content = "import random\n\ndef test_x():\n    return random.randint(0, 9)\n"
    smells = analyzer.scan_file_for_smells(Path("tests/fake.py"), content)
    cats = {s.category for s in smells}
    assert "unseeded_random" in cats


def test_scan_file_for_smells_exempts_random_when_seeded(analyzer):
    content = "import random\nrandom.seed(42)\n\ndef test_x():\n    return random.randint(0, 9)\n"
    smells = analyzer.scan_file_for_smells(Path("tests/fake.py"), content)
    cats = {s.category for s in smells}
    assert "unseeded_random" not in cats


def test_scan_file_for_smells_detects_real_network(analyzer):
    content = "import httpx\n\ndef test_x():\n    httpx.get('https://example.com')\n"
    smells = analyzer.scan_file_for_smells(Path("tests/fake.py"), content)
    cats = {s.category for s in smells}
    assert "real_network" in cats


def test_scan_file_for_smells_exempts_mocked_network(analyzer):
    content = "def test_x(monkeypatch):\n    monkeypatch.setattr(httpx, 'get', mock)\n"
    smells = analyzer.scan_file_for_smells(Path("tests/fake.py"), content)
    {s.category for s in smells}
    # The line literally references httpx.get but is exempt due to monkeypatch.
    # We assert the line itself is not flagged as real_network.
    real_net_lines = [s.line for s in smells if s.category == "real_network"]
    assert real_net_lines == []


def test_scan_file_for_smells_skips_comments_and_blank_lines(analyzer):
    content = "# time.sleep(1) — comment\n\ndef test_x():\n    pass\n"
    smells = analyzer.scan_file_for_smells(Path("tests/fake.py"), content)
    assert smells == []


# ---------------------------------------------------------------------------
# Markdown rendering smoke
# ---------------------------------------------------------------------------


def test_render_markdown_clean_report(analyzer):
    report = analyzer.AnalyzerReport(static_only=True)
    out = analyzer.render_markdown(report)
    assert "# Test Flakiness Baseline Report" in out
    assert "## Static smells" in out
    assert "_None detected._" in out
    assert "## Action items" in out


def test_render_markdown_includes_flaky_table(analyzer):
    report = analyzer.AnalyzerReport(static_only=False)
    report.runs = [
        _make_run(analyzer, 1, {"a::t": "passed", "b::t": "failed"}),
        _make_run(analyzer, 2, {"a::t": "passed", "b::t": "passed"}),
    ]
    report.aggregated = analyzer.aggregate_outcomes(report.runs)
    report.flaky = analyzer.classify_flaky(report.aggregated)
    out = analyzer.render_markdown(report)
    assert "Flaky tests" in out
    assert "`b::t`" in out


def test_render_markdown_static_smells_table(analyzer):
    report = analyzer.AnalyzerReport(static_only=True)
    report.smells = [
        analyzer.StaticSmell(file="tests/fake.py", line=4, category="real_sleep", snippet="time.sleep(1)"),
    ]
    out = analyzer.render_markdown(report)
    assert "| `real_sleep` | 1 |" in out
    assert "tests/fake.py:4" in out
