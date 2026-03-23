"""Tests for the roadmap entropy detector."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from twag.cli import cli
from twag.entropy import (
    EntropyReport,
    analyze_entropy,
    churn_dispersion,
    classify_commit,
    count_todos,
    doc_staleness,
    get_commit_messages,
    get_file_churn,
    get_surface_area_delta,
    shannon_entropy,
)

# --- classify_commit ---


def test_classify_feat():
    """`feat:` prefix maps to 'feature' topic."""
    assert classify_commit("feat: add login page") == "feature"


def test_classify_fix():
    """`fix:` prefix maps to 'bugfix' topic."""
    assert classify_commit("fix: resolve crash on startup") == "bugfix"


def test_classify_scoped():
    """`feat(scope):` prefix is recognized."""
    assert classify_commit("feat(auth): add OAuth support") == "feature"


def test_classify_breaking():
    """`feat!:` breaking change prefix is recognized."""
    assert classify_commit("feat!: redesign API") == "feature"


def test_classify_docs():
    """`docs:` prefix maps to 'docs' topic."""
    assert classify_commit("docs: update README") == "docs"


def test_classify_chore():
    """`chore:` prefix maps to 'chore' topic."""
    assert classify_commit("chore: bump dependencies") == "chore"


def test_classify_unknown():
    """Non-conventional messages map to 'other'."""
    assert classify_commit("just a random commit message") == "other"


def test_classify_refactor():
    """`refactor:` prefix maps to 'refactor' topic."""
    assert classify_commit("refactor: extract helper function") == "refactor"


# --- shannon_entropy ---


def test_shannon_entropy_uniform():
    """Uniform distribution over N categories yields entropy ~1.0."""
    counts = {"a": 10, "b": 10, "c": 10, "d": 10}
    e = shannon_entropy(counts)
    assert 0.99 <= e <= 1.0


def test_shannon_entropy_concentrated():
    """Single-category distribution yields entropy 0.0."""
    counts = {"a": 100}
    assert shannon_entropy(counts) == 0.0


def test_shannon_entropy_empty():
    """Empty distribution yields entropy 0.0."""
    assert shannon_entropy({}) == 0.0


def test_shannon_entropy_skewed():
    """Skewed distribution yields low but nonzero entropy."""
    counts = {"a": 90, "b": 5, "c": 3, "d": 2}
    e = shannon_entropy(counts)
    assert 0.0 < e < 0.7


# --- churn_dispersion ---


def test_churn_dispersion_focused():
    """All churn in one file yields dispersion 0.0."""
    churn = [("main.py", 100)]
    assert churn_dispersion(churn) == 0.0


def test_churn_dispersion_empty():
    """No churn yields dispersion 0.0."""
    assert churn_dispersion([]) == 0.0


def test_churn_dispersion_spread():
    """Evenly spread churn yields high dispersion."""
    churn = [(f"file{i}.py", 1) for i in range(100)]
    d = churn_dispersion(churn)
    assert d > 0.8


# --- get_commit_messages with mocked git ---


def test_get_commit_messages_parses_output():
    """`get_commit_messages` splits git log output into lines."""
    fake_output = "feat: add login\nfix: crash\nchore: bump deps\n"
    with patch("twag.entropy._run_git", return_value=fake_output):
        msgs = get_commit_messages(days=30)
    assert msgs == ["feat: add login", "fix: crash", "chore: bump deps"]


def test_get_commit_messages_empty():
    """`get_commit_messages` returns empty list for no commits."""
    with patch("twag.entropy._run_git", return_value=""):
        msgs = get_commit_messages(days=30)
    assert msgs == []


# --- get_file_churn with mocked git ---


def test_get_file_churn_counts():
    """`get_file_churn` counts file appearances."""
    fake_output = "a.py\nb.py\na.py\na.py\nb.py\nc.py\n"
    with patch("twag.entropy._run_git", return_value=fake_output):
        churn = get_file_churn(days=30)
    assert churn[0] == ("a.py", 3)
    assert churn[1] == ("b.py", 2)
    assert churn[2] == ("c.py", 1)


# --- get_surface_area_delta with mocked git ---


def test_surface_area_delta():
    """`get_surface_area_delta` computes added minus deleted."""
    call_count = [0]

    def fake_git(args, repo_path=None):
        call_count[0] += 1
        if "--diff-filter=A" in args:
            return "new1.py\nnew2.py\nnew3.py\n"
        if "--diff-filter=D" in args:
            return "old1.py\n"
        return ""

    with patch("twag.entropy._run_git", side_effect=fake_git):
        delta = get_surface_area_delta(days=30)
    assert delta == 2


# --- count_todos with mocked filesystem ---


def test_count_todos(tmp_path):
    """`count_todos` counts TODO/FIXME markers in source files."""
    (tmp_path / "code.py").write_text("# TODO: fix this\nx = 1\n# FIXME: broken\n")
    (tmp_path / "clean.py").write_text("x = 1\ny = 2\n")
    assert count_todos(str(tmp_path)) == 2


def test_count_todos_skips_hidden(tmp_path):
    """`count_todos` skips hidden directories."""
    hidden = tmp_path / ".git"
    hidden.mkdir()
    (hidden / "code.py").write_text("# TODO: in git\n")
    (tmp_path / "real.py").write_text("# TODO: real\n")
    assert count_todos(str(tmp_path)) == 1


# --- doc_staleness with mocked git ---


def test_doc_staleness_all_fresh():
    """`doc_staleness` returns 0.0 when all docs are updated."""

    def fake_git(args, repo_path=None):
        if "ls-files" in args:
            return "README.md\ncode.py\n"
        return "README.md\ncode.py\n"

    with patch("twag.entropy._run_git", side_effect=fake_git):
        ratio = doc_staleness(days=30)
    assert ratio == 0.0


def test_doc_staleness_all_stale():
    """`doc_staleness` returns 1.0 when no docs are updated but code is."""

    def fake_git(args, repo_path=None):
        if "ls-files" in args:
            return "README.md\nDOCS.md\ncode.py\n"
        return "code.py\n"

    with patch("twag.entropy._run_git", side_effect=fake_git):
        ratio = doc_staleness(days=30)
    assert ratio == 1.0


# --- analyze_entropy integration ---


def test_analyze_entropy_returns_report():
    """`analyze_entropy` returns an EntropyReport with all fields populated."""
    with (
        patch("twag.entropy.get_commit_messages", return_value=["feat: a", "fix: b", "feat: c"]),
        patch("twag.entropy.get_file_churn", return_value=[("x.py", 5), ("y.py", 3)]),
        patch("twag.entropy.get_surface_area_delta", return_value=5),
        patch("twag.entropy.count_todos", return_value=10),
        patch("twag.entropy.doc_staleness", return_value=0.3),
    ):
        report = analyze_entropy(days=30)

    assert isinstance(report, EntropyReport)
    assert 0 <= report.overall_score <= 100
    assert report.topic_counts["feature"] == 2
    assert report.topic_counts["bugfix"] == 1
    assert report.todo_accumulation == 10
    assert report.surface_area_delta == 5


# --- CLI command ---


def test_entropy_cli_runs():
    """`twag entropy` command exits successfully."""
    with (
        patch("twag.entropy.get_commit_messages", return_value=["feat: a", "fix: b"]),
        patch("twag.entropy.get_file_churn", return_value=[("x.py", 5)]),
        patch("twag.entropy.get_surface_area_delta", return_value=2),
        patch("twag.entropy.count_todos", return_value=5),
        patch("twag.entropy.doc_staleness", return_value=0.2),
    ):
        runner = CliRunner()
        result = runner.invoke(cli, ["entropy"])
    assert result.exit_code == 0
    assert "Entropy Report" in result.output


def test_entropy_cli_json():
    """`twag entropy --json` outputs valid JSON."""
    import json

    with (
        patch("twag.entropy.get_commit_messages", return_value=["feat: a"]),
        patch("twag.entropy.get_file_churn", return_value=[]),
        patch("twag.entropy.get_surface_area_delta", return_value=0),
        patch("twag.entropy.count_todos", return_value=0),
        patch("twag.entropy.doc_staleness", return_value=0.0),
    ):
        runner = CliRunner()
        result = runner.invoke(cli, ["entropy", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "overall_score" in data
    assert "recommendations" in data
