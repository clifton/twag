"""Tests for the roadmap entropy detector."""

from __future__ import annotations

import math
import tempfile

import pytest

from twag.entropy import (
    CommitInfo,
    build_report,
    detect_drift,
    file_to_area,
    format_text_report,
    load_roadmap,
    max_entropy,
    shannon_entropy,
)

# ---------------------------------------------------------------------------
# file_to_area
# ---------------------------------------------------------------------------


class TestFileToArea:
    def test_fetcher(self):
        assert file_to_area("twag/fetcher/bird.py") == "fetcher"

    def test_processor(self):
        assert file_to_area("twag/processor/pipeline.py") == "processor"

    def test_scorer(self):
        assert file_to_area("twag/scorer/client.py") == "scorer"

    def test_web_frontend(self):
        assert file_to_area("twag/web/frontend/src/App.tsx") == "frontend"

    def test_web_backend(self):
        assert file_to_area("twag/web/routes/tweets.py") == "web"

    def test_cli(self):
        assert file_to_area("twag/cli/fetch.py") == "cli"

    def test_db(self):
        assert file_to_area("twag/db/schema.py") == "db"

    def test_scripts(self):
        assert file_to_area("scripts/roadmap_entropy.py") == "scripts"

    def test_tests(self):
        assert file_to_area("tests/test_roadmap_entropy.py") == "tests"

    def test_docs(self):
        assert file_to_area("README.md") == "docs"
        assert file_to_area("INSTALL.md") == "docs"

    def test_config(self):
        assert file_to_area("pyproject.toml") == "config"
        assert file_to_area(".roadmap.yml") == "config"

    def test_core_module(self):
        assert file_to_area("twag/auth.py") == "core"

    def test_other(self):
        assert file_to_area("random_file.bin") == "other"


# ---------------------------------------------------------------------------
# Entropy calculation
# ---------------------------------------------------------------------------


class TestShannonEntropy:
    def test_uniform_two(self):
        assert shannon_entropy({"a": 1, "b": 1}) == pytest.approx(1.0)

    def test_uniform_four(self):
        assert shannon_entropy({"a": 1, "b": 1, "c": 1, "d": 1}) == pytest.approx(2.0)

    def test_single_category(self):
        assert shannon_entropy({"a": 10}) == pytest.approx(0.0)

    def test_empty(self):
        assert shannon_entropy({}) == 0.0

    def test_skewed(self):
        # 90/10 split
        e = shannon_entropy({"a": 9, "b": 1})
        assert 0 < e < 1.0

    def test_max_entropy(self):
        assert max_entropy(1) == 0.0
        assert max_entropy(8) == pytest.approx(math.log2(8))


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


def _make_commits(areas_sequence: list[list[str]]) -> list[CommitInfo]:
    """Create synthetic CommitInfo objects from a list of area-lists."""
    commits = []
    for i, areas in enumerate(areas_sequence):
        files = [f"twag/{a}/fake.py" for a in areas]
        commits.append(CommitInfo(sha=f"{i:040x}", subject=f"commit {i}", files=files, areas=set(areas)))
    return commits


class TestDetectDrift:
    def test_no_commits(self):
        assert detect_drift([]) == []

    def test_new_area_detected(self):
        # First half: only fetcher. Second half: fetcher + web.
        commits = _make_commits(
            [
                ["fetcher"],
                ["fetcher"],
                ["fetcher"],
                ["fetcher"],
                ["fetcher"],
                ["fetcher"],
                ["web"],
                ["web"],
            ]
        )
        signals = detect_drift(commits)
        new_area_signals = [s for s in signals if s.kind == "new_area"]
        assert len(new_area_signals) == 1
        assert "web" in new_area_signals[0].details["areas"]

    def test_concentration_shift(self):
        # First half: all fetcher. Second half: all web.
        commits = _make_commits(
            [
                ["fetcher"],
                ["fetcher"],
                ["fetcher"],
                ["fetcher"],
                ["web"],
                ["web"],
                ["web"],
                ["web"],
            ]
        )
        signals = detect_drift(commits)
        shift_signals = [s for s in signals if s.kind == "concentration_shift"]
        assert len(shift_signals) >= 1

    def test_high_entropy_commit(self):
        # One commit touching many areas
        many_areas = ["fetcher", "processor", "scorer", "web", "db", "cli"]
        commits = [
            CommitInfo(
                sha="a" * 40,
                subject="big refactor",
                files=[f"twag/{a}/x.py" for a in many_areas],
                areas=set(many_areas),
            )
        ]
        signals = detect_drift(commits, high_entropy_threshold=1.0)
        high_e = [s for s in signals if s.kind == "high_entropy_commit"]
        assert len(high_e) == 1

    def test_roadmap_underweight(self):
        # All work in fetcher, but roadmap expects work in scorer
        commits = _make_commits([["fetcher"]] * 10)
        signals = detect_drift(commits, roadmap_weights={"fetcher": 0.5, "scorer": 0.5})
        under = [s for s in signals if s.kind == "roadmap_underweight"]
        assert len(under) == 1
        assert under[0].details["area"] == "scorer"


# ---------------------------------------------------------------------------
# Roadmap loading
# ---------------------------------------------------------------------------


class TestLoadRoadmap:
    def test_missing_file(self):
        assert load_roadmap("/nonexistent/.roadmap.yml") is None

    def test_valid_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("focus_areas:\n  fetcher: 0.3\n  web: 0.2\n")
            f.flush()
            result = load_roadmap(f.name)
        assert result == {"fetcher": 0.3, "web": 0.2}

    def test_invalid_content(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("just a string\n")
            f.flush()
            assert load_roadmap(f.name) is None


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


class TestReport:
    def test_build_report_structure(self):
        commits = _make_commits([["fetcher"], ["web"], ["web"]])
        signals = detect_drift(commits)
        report = build_report(commits, signals, days=7)

        assert report["window_days"] == 7
        assert report["total_commits"] == 3
        assert "fetcher" in report["area_breakdown"]
        assert "web" in report["area_breakdown"]
        assert report["entropy"] > 0
        assert isinstance(report["drift_signals"], list)

    def test_format_text_report(self):
        commits = _make_commits([["fetcher"], ["web"]])
        signals = detect_drift(commits)
        report = build_report(commits, signals, days=14)
        text = format_text_report(report)

        assert "Roadmap Entropy Report" in text
        assert "14 days" in text
        assert "fetcher" in text

    def test_empty_report(self):
        report = build_report([], [], days=30)
        assert report["total_commits"] == 0
        assert report["entropy"] == 0.0
        text = format_text_report(report)
        assert "No drift signals detected" in text
