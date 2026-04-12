"""Tests for the pure-logic functions in scripts/roadmap_entropy.py."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from roadmap_entropy import (
    churn_concentration,
    classify_commit_topic,
    classify_file,
    detect_anomalies,
    gini_coefficient,
    new_files,
    shannon_entropy,
    subsystem_spread,
    topic_distribution,
    week_boundaries,
)

# ---------------------------------------------------------------------------
# classify_file
# ---------------------------------------------------------------------------


class TestClassifyFile:
    def test_subsystem_packages(self):
        assert classify_file("twag/cli/main.py") == "twag/cli"
        assert classify_file("twag/db/schema.py") == "twag/db"
        assert classify_file("twag/web/app.py") == "twag/web"

    def test_top_level_modules(self):
        assert classify_file("twag/auth.py") == "twag/auth.py"
        assert classify_file("twag/notifier.py") == "twag/notifier.py"

    def test_unknown_twag_file(self):
        assert classify_file("twag/brand_new.py") == "twag/other"

    def test_tests_and_scripts(self):
        assert classify_file("tests/test_foo.py") == "tests"
        assert classify_file("scripts/run.py") == "scripts"

    def test_root_files(self):
        assert classify_file("pyproject.toml") == "root"
        assert classify_file("README.md") == "root"


# ---------------------------------------------------------------------------
# gini_coefficient
# ---------------------------------------------------------------------------


class TestGiniCoefficient:
    def test_perfect_equality(self):
        assert gini_coefficient([10, 10, 10, 10]) == 0.0

    def test_empty(self):
        assert gini_coefficient([]) == 0.0

    def test_all_zeros(self):
        assert gini_coefficient([0, 0, 0]) == 0.0

    def test_maximum_inequality(self):
        gini = gini_coefficient([0, 0, 0, 100])
        assert gini > 0.7

    def test_moderate_inequality(self):
        gini = gini_coefficient([1, 2, 3, 4, 5])
        assert 0.1 < gini < 0.5

    def test_single_value(self):
        assert gini_coefficient([42]) == 0.0


# ---------------------------------------------------------------------------
# shannon_entropy
# ---------------------------------------------------------------------------


class TestShannonEntropy:
    def test_single_category(self):
        assert shannon_entropy({"feat": 10}) == 0.0

    def test_uniform_two(self):
        ent = shannon_entropy({"a": 5, "b": 5})
        assert abs(ent - 1.0) < 0.01

    def test_empty(self):
        assert shannon_entropy({}) == 0.0

    def test_skewed(self):
        ent = shannon_entropy({"feat": 90, "fix": 5, "docs": 5})
        assert 0.0 < ent < 1.5


# ---------------------------------------------------------------------------
# classify_commit_topic
# ---------------------------------------------------------------------------


class TestClassifyCommitTopic:
    def test_feature_commit(self):
        assert classify_commit_topic("Add new scoring pipeline") == "feat"

    def test_fix_commit(self):
        assert classify_commit_topic("fix: resolve null pointer bug") == "fix"

    def test_refactor_commit(self):
        assert classify_commit_topic("refactor auth module") == "refactor"

    def test_test_commit(self):
        assert classify_commit_topic("add test coverage for scorer") == "test"

    def test_unknown_commit(self):
        assert classify_commit_topic("bump version to 2.0") == "deps"

    def test_truly_unknown(self):
        assert classify_commit_topic("v2.0.0") == "other"


# ---------------------------------------------------------------------------
# subsystem_spread
# ---------------------------------------------------------------------------


class TestSubsystemSpread:
    def test_single_subsystem_commit(self):
        commits = [{"files": ["twag/cli/main.py", "twag/cli/utils.py"], "subject": "x"}]
        result = subsystem_spread(commits)
        assert result["avg_subsystems_per_commit"] == 1.0
        assert result["max_subsystems_in_commit"] == 1

    def test_multi_subsystem_commit(self):
        commits = [{"files": ["twag/cli/main.py", "twag/db/schema.py", "twag/web/app.py"], "subject": "x"}]
        result = subsystem_spread(commits)
        assert result["avg_subsystems_per_commit"] == 3.0

    def test_empty(self):
        result = subsystem_spread([])
        assert result["avg_subsystems_per_commit"] == 0.0


# ---------------------------------------------------------------------------
# new_files
# ---------------------------------------------------------------------------


class TestNewFiles:
    def test_identifies_new_files(self):
        known: set[str] = {"twag/auth.py"}
        commits = [{"files": ["twag/auth.py", "twag/brand_new.py"]}]
        introduced = new_files(commits, known)
        assert introduced == ["twag/brand_new.py"]
        assert "twag/brand_new.py" in known

    def test_no_new_files(self):
        known: set[str] = {"a.py", "b.py"}
        commits = [{"files": ["a.py", "b.py"]}]
        assert new_files(commits, known) == []


# ---------------------------------------------------------------------------
# churn_concentration
# ---------------------------------------------------------------------------


class TestChurnConcentration:
    def test_returns_gini(self):
        commits = [
            {"files": ["twag/cli/a.py", "twag/cli/b.py", "twag/db/c.py"]},
        ]
        result = churn_concentration(commits)
        assert "gini" in result
        assert isinstance(result["gini"], float)


# ---------------------------------------------------------------------------
# topic_distribution
# ---------------------------------------------------------------------------


class TestTopicDistribution:
    def test_counts_topics(self):
        commits = [
            {"subject": "add new feature"},
            {"subject": "fix bug in scorer"},
            {"subject": "add another feature"},
        ]
        dist = topic_distribution(commits)
        assert dist["feat"] == 2
        assert dist["fix"] == 1


# ---------------------------------------------------------------------------
# detect_anomalies
# ---------------------------------------------------------------------------


class TestDetectAnomalies:
    def test_no_anomalies_when_quiet(self):
        flags = detect_anomalies(
            "week of 2026-01-01",
            spread={"subsystem_touch_counts": {"twag/cli": 2}, "avg_subsystems_per_commit": 1.0},
            new_file_count=1,
            dep_info={"deps_net": 0},
            churn={"gini": 0.3},
            topic_entropy=1.0,
            total_subsystems=18,
        )
        assert flags == []

    def test_flags_high_spread(self):
        counts = {f"sub{i}": 1 for i in range(14)}
        flags = detect_anomalies(
            "week of 2026-01-01",
            spread={"subsystem_touch_counts": counts, "avg_subsystems_per_commit": 1.0},
            new_file_count=0,
            dep_info={"deps_net": 0},
            churn={"gini": 0.3},
            topic_entropy=1.0,
            total_subsystems=18,
        )
        assert any("subsystems" in f for f in flags)

    def test_flags_many_new_files(self):
        flags = detect_anomalies(
            "week of 2026-01-01",
            spread={"subsystem_touch_counts": {}, "avg_subsystems_per_commit": 1.0},
            new_file_count=5,
            dep_info={"deps_net": 0},
            churn={"gini": 0.3},
            topic_entropy=1.0,
            total_subsystems=18,
        )
        assert any("new files" in f for f in flags)

    def test_flags_dep_growth(self):
        flags = detect_anomalies(
            "week of 2026-01-01",
            spread={"subsystem_touch_counts": {}, "avg_subsystems_per_commit": 1.0},
            new_file_count=0,
            dep_info={"deps_net": 4},
            churn={"gini": 0.3},
            topic_entropy=1.0,
            total_subsystems=18,
        )
        assert any("dependencies" in f for f in flags)

    def test_flags_high_topic_entropy(self):
        flags = detect_anomalies(
            "week of 2026-01-01",
            spread={"subsystem_touch_counts": {}, "avg_subsystems_per_commit": 1.0},
            new_file_count=0,
            dep_info={"deps_net": 0},
            churn={"gini": 0.3},
            topic_entropy=3.0,
            total_subsystems=18,
        )
        assert any("topic entropy" in f for f in flags)


# ---------------------------------------------------------------------------
# week_boundaries
# ---------------------------------------------------------------------------


class TestWeekBoundaries:
    def test_returns_correct_count(self):
        bounds = week_boundaries(4)
        assert len(bounds) == 4

    def test_labels_are_ordered(self):
        bounds = week_boundaries(4)
        labels = [b[0] for b in bounds]
        assert labels == sorted(labels)

    def test_each_window_is_one_week(self):
        from datetime import date

        bounds = week_boundaries(3)
        for _, since, until in bounds:
            s = date.fromisoformat(since)
            u = date.fromisoformat(until)
            assert (u - s).days == 7
