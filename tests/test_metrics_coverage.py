"""Tests for twag.metrics_coverage — static AST-based instrumentation analyzer."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from twag.metrics_coverage import (
    SUBSYSTEM_MAP,
    analyze_coverage,
)


def _write(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(body).lstrip(), encoding="utf-8")


def _make_pkg(tmp_path: Path) -> Path:
    """Create a minimal twag-shaped package skeleton at tmp_path/twag."""
    root = tmp_path / "twag"
    _write(root, "__init__.py", "")
    return root


def test_detects_collector_methods(tmp_path: Path) -> None:
    root = _make_pkg(tmp_path)
    _write(
        root,
        "fetcher/bird_cli.py",
        """
        from twag.metrics import get_collector
        def go():
            m = get_collector()
            m.inc("fetcher.calls")
            m.observe("fetcher.latency_seconds", 0.1)
            m.set_gauge("fetcher.in_flight", 1.0)
        """,
    )
    _write(root, "fetcher/__init__.py", "")

    report = analyze_coverage(root)
    apis = sorted(s.api for s in report.call_sites)
    assert apis == ["inc", "observe", "set_gauge"]
    assert report.subsystems["fetcher"].call_sites == 3
    assert "fetcher.bird_cli" in report.subsystems["fetcher"].instrumented_modules
    assert "fetcher.calls" in report.subsystems["fetcher"].metric_names


def test_detects_module_level_funcs(tmp_path: Path) -> None:
    root = _make_pkg(tmp_path)
    _write(
        root,
        "scorer/llm_client.py",
        """
        from twag.metrics import counter, histogram, timer
        def call():
            counter("scorer.gemini.calls")
            histogram("scorer.gemini.latency_seconds", 0.4)
            with timer("scorer.gemini.timer"):
                pass
        """,
    )
    _write(root, "scorer/__init__.py", "")

    report = analyze_coverage(root)
    apis = sorted(s.api for s in report.call_sites)
    assert apis == ["counter", "histogram", "timer"]
    assert report.subsystems["scorer"].call_sites == 3


def test_maps_name_prefix_to_subsystem(tmp_path: Path) -> None:
    root = _make_pkg(tmp_path)
    # Module path is not under scorer/, but metric name is — we still attribute
    # the call site to the scorer subsystem via the metric prefix.
    _write(
        root,
        "helpers.py",
        """
        from twag.metrics import counter
        def helper():
            counter("scorer.helper.calls")
        """,
    )

    report = analyze_coverage(root)
    assert report.subsystems["scorer"].call_sites == 1
    assert "scorer.helper.calls" in report.subsystems["scorer"].metric_names


def test_flags_prefix_mismatch(tmp_path: Path) -> None:
    root = _make_pkg(tmp_path)
    # File lives under fetcher/ but records a pipeline.* metric.
    _write(
        root,
        "fetcher/odd.py",
        """
        from twag.metrics import counter
        def go():
            counter("pipeline.something")
        """,
    )
    _write(root, "fetcher/__init__.py", "")

    report = analyze_coverage(root)
    fetcher_cov = report.subsystems["fetcher"]
    assert len(fetcher_cov.prefix_mismatches) == 1
    site = fetcher_cov.prefix_mismatches[0]
    assert site.inferred_subsystem == "fetcher"
    assert site.name_subsystem == "pipeline"
    assert site.metric_name == "pipeline.something"


def test_handles_files_with_no_metrics(tmp_path: Path) -> None:
    root = _make_pkg(tmp_path)
    _write(
        root,
        "scorer/utils.py",
        """
        def add(a, b):
            return a + b
        """,
    )
    _write(root, "scorer/__init__.py", "")

    report = analyze_coverage(root)
    assert report.call_sites == []
    # The scorer/ subsystem has 2 modules (utils + __init__) but no instrumentation.
    assert report.subsystems["scorer"].call_sites == 0
    assert report.subsystems["scorer"].total_modules >= 1
    assert any(m.startswith("scorer") for m in report.uninstrumented_modules)


def test_real_twag_tree_has_known_subsystems_instrumented() -> None:
    """End-to-end: scanning the real twag/ tree finds known instrumented subsystems."""
    root = Path(__file__).resolve().parents[1] / "twag"
    if not root.exists():
        pytest.skip("twag source tree not available")
    report = analyze_coverage(root)

    # These four are known to be instrumented in the current codebase.
    for name in ("scorer", "pipeline", "fetcher", "web"):
        assert report.subsystems[name].call_sites > 0, f"{name} should have call sites"
        assert report.subsystems[name].instrumented_modules, f"{name} should have modules"

    # Spot-check a known metric name.
    assert any(m.startswith("scorer.") for cov in report.subsystems.values() for m in cov.metric_names)

    # The metrics module itself should not be reported as uninstrumented.
    assert "metrics" not in report.uninstrumented_modules


def test_subsystem_map_is_single_source_of_truth() -> None:
    """Every subsystem in SUBSYSTEM_MAP appears in the report keyed by name."""
    root = Path(__file__).resolve().parents[1] / "twag"
    if not root.exists():
        pytest.skip("twag source tree not available")
    report = analyze_coverage(root)
    assert set(report.subsystems.keys()) == set(SUBSYSTEM_MAP.keys())
