"""Tests for the roadmap entropy detector."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load scripts/roadmap_entropy.py directly so ty doesn't need it on the module path.
_spec = importlib.util.spec_from_file_location(
    "roadmap_entropy",
    Path(__file__).resolve().parent.parent / "scripts" / "roadmap_entropy.py",
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules["roadmap_entropy"] = _mod
_spec.loader.exec_module(_mod)

CommitInfo = _mod.CommitInfo
build_keywords = _mod.build_keywords
classify_commit = _mod.classify_commit
compute_metrics = _mod.compute_metrics
parse_roadmap = _mod.parse_roadmap

# ---------------------------------------------------------------------------
# ROADMAP parsing
# ---------------------------------------------------------------------------

SAMPLE_ROADMAP = """\
# Roadmap

## Themes

### pipeline-reliability
Retries, error handling, parallelism.

### scoring-quality
LLM prompt tuning and model upgrades.

### web-feed
FastAPI routes and React frontend.

### docs
Keep documentation in sync.

## Archive

### old-theme
No longer active.
"""


class TestParseRoadmap:
    def test_extracts_themes(self):
        themes = parse_roadmap(SAMPLE_ROADMAP)
        assert themes == ["pipeline-reliability", "scoring-quality", "web-feed", "docs"]

    def test_stops_at_next_h2(self):
        themes = parse_roadmap(SAMPLE_ROADMAP)
        assert "old-theme" not in themes

    def test_empty_input(self):
        assert parse_roadmap("") == []

    def test_no_themes_section(self):
        assert parse_roadmap("# Roadmap\n\nSome text.\n") == []


class TestBuildKeywords:
    def test_splits_hyphenated(self):
        kw = build_keywords(["pipeline-reliability"])
        assert "pipeline" in kw["pipeline-reliability"]
        assert "reliability" in kw["pipeline-reliability"]

    def test_drops_short_tokens(self):
        kw = build_keywords(["cli-ux"])
        # "ux" is only 2 chars, should be dropped
        assert "ux" not in kw["cli-ux"]
        assert "cli" in kw["cli-ux"]


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

THEMES = ["pipeline-reliability", "scoring-quality", "web-feed", "docs", "ops-automation"]
KEYWORDS = build_keywords(THEMES)


class TestClassifyCommit:
    def test_exact_slug_in_subject(self):
        c = CommitInfo(sha="abc", subject="fix: pipeline-reliability retry bug")
        assert classify_commit(c, THEMES, KEYWORDS) == "pipeline-reliability"

    def test_keyword_match(self):
        c = CommitInfo(sha="abc", subject="improve scoring prompt accuracy")
        assert classify_commit(c, THEMES, KEYWORDS) == "scoring-quality"

    def test_path_based_fallback(self):
        c = CommitInfo(sha="abc", subject="misc cleanup", files=["twag/web/routes/tweets.py"])
        assert classify_commit(c, THEMES, KEYWORDS) == "web-feed"

    def test_unplanned(self):
        c = CommitInfo(sha="abc", subject="random experiment", files=["random_thing.py"])
        assert classify_commit(c, THEMES, KEYWORDS) is None

    def test_docs_match(self):
        c = CommitInfo(sha="abc", subject="update guides", files=["README.md"])
        assert classify_commit(c, THEMES, KEYWORDS) == "docs"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class TestComputeMetrics:
    def test_empty_commits(self):
        report = compute_metrics([], THEMES, KEYWORDS)
        assert report.total_commits == 0
        assert report.drift_score == 0.0

    def test_all_aligned(self):
        commits = [
            CommitInfo(sha="a", subject="pipeline-reliability fix", files=["twag/fetcher/x.py"]),
            CommitInfo(sha="b", subject="scoring-quality tune", files=["twag/scorer/y.py"]),
        ]
        report = compute_metrics(commits, THEMES, KEYWORDS)
        assert report.total_commits == 2
        assert report.aligned_commits == 2
        assert report.unplanned_commits == 0
        assert report.unplanned_ratio == 0.0

    def test_all_unplanned(self):
        commits = [
            CommitInfo(sha="a", subject="random stuff", files=["random.py"]),
            CommitInfo(sha="b", subject="another thing", files=["another.py"]),
        ]
        report = compute_metrics(commits, THEMES, KEYWORDS)
        assert report.unplanned_commits == 2
        assert report.unplanned_ratio == 1.0
        assert report.drift_score > 0.0

    def test_drift_score_bounded(self):
        commits = [CommitInfo(sha=str(i), subject="chaos", files=[f"dir{i}/file{i}.py"]) for i in range(20)]
        report = compute_metrics(commits, THEMES, KEYWORDS)
        assert 0.0 <= report.drift_score <= 1.0

    def test_mixed_alignment(self):
        commits = [
            CommitInfo(sha="a", subject="pipeline-reliability fix", files=["twag/fetcher/x.py"]),
            CommitInfo(sha="b", subject="random experiment", files=["random.py"]),
        ]
        report = compute_metrics(commits, THEMES, KEYWORDS)
        assert report.aligned_commits == 1
        assert report.unplanned_commits == 1
        assert report.unplanned_ratio == 0.5
