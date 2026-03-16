"""Roadmap entropy detector — analyzes git history for scope creep and drift signals."""

from __future__ import annotations

import math
import os
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# --- Data structures ---


@dataclass
class DriftIndicator:
    """A single signal of scope creep or drift."""

    category: str
    description: str
    severity: str  # "low", "medium", "high"
    score_contribution: float


@dataclass
class EntropyReport:
    """Full entropy analysis result."""

    overall_score: float  # 0-100
    commit_topic_entropy: float
    file_churn_dispersion: float
    surface_area_delta: int
    todo_accumulation: int
    doc_staleness_ratio: float
    drift_indicators: list[DriftIndicator] = field(default_factory=list)
    topic_counts: dict[str, int] = field(default_factory=dict)
    churn_hotspots: list[tuple[str, int]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# --- Conventional commit prefix mapping ---

TOPIC_PREFIXES = {
    "feat": "feature",
    "fix": "bugfix",
    "docs": "docs",
    "style": "style",
    "refactor": "refactor",
    "perf": "perf",
    "test": "test",
    "chore": "chore",
    "build": "build",
    "ci": "ci",
}

_PREFIX_RE = re.compile(r"^(\w+)(?:\(.*?\))?[!]?:\s")


def classify_commit(message: str) -> str:
    """Classify a commit message by conventional-commit prefix."""
    m = _PREFIX_RE.match(message)
    if m:
        prefix = m.group(1).lower()
        return TOPIC_PREFIXES.get(prefix, "other")
    return "other"


# --- Git helpers ---


def _run_git(args: list[str], repo_path: str | None = None) -> str:
    """Run a git command and return stdout."""
    cmd = ["git"]
    if repo_path:
        cmd += ["-C", repo_path]
    cmd += args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    return result.stdout


def get_commit_messages(days: int = 90, repo_path: str | None = None) -> list[str]:
    """Return commit messages from the last N days."""
    since = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    output = _run_git(["log", f"--since={since}", "--pretty=format:%s"], repo_path)
    return [line for line in output.strip().splitlines() if line]


def get_file_churn(days: int = 90, repo_path: str | None = None) -> list[tuple[str, int]]:
    """Return (filepath, change_count) sorted by most changed."""
    since = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    output = _run_git(["log", f"--since={since}", "--pretty=format:", "--name-only"], repo_path)
    counts: Counter[str] = Counter()
    for line in output.strip().splitlines():
        line = line.strip()
        if line:
            counts[line] += 1
    return counts.most_common()


def get_surface_area_delta(days: int = 90, repo_path: str | None = None) -> int:
    """Count net new files added in the period (added minus deleted)."""
    since = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    output = _run_git(
        ["log", f"--since={since}", "--diff-filter=A", "--pretty=format:", "--name-only"],
        repo_path,
    )
    added = len([line for line in output.strip().splitlines() if line.strip()])
    output = _run_git(
        ["log", f"--since={since}", "--diff-filter=D", "--pretty=format:", "--name-only"],
        repo_path,
    )
    deleted = len([line for line in output.strip().splitlines() if line.strip()])
    return added - deleted


# --- Code scanning ---


_TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)


def count_todos(repo_path: str | None = None) -> int:
    """Count TODO/FIXME/HACK/XXX comments in the codebase."""
    root = repo_path or os.getcwd()
    count = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        # Skip hidden dirs and common non-source dirs
        parts = dirpath.split(os.sep)
        if any(
            p.startswith(".") or p in ("node_modules", "__pycache__", "venv", ".venv", "dist", "build") for p in parts
        ):
            continue
        for fname in filenames:
            if not fname.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".txt")):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if _TODO_RE.search(line):
                            count += 1
            except OSError:
                continue
    return count


def doc_staleness(days: int = 90, repo_path: str | None = None) -> float:
    """Return ratio of doc files NOT updated vs code files updated in the period.

    Returns a value between 0.0 (docs fully up-to-date) and 1.0 (all docs stale).
    If there are no doc files in the repo, returns 0.0.
    """
    since = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    output = _run_git(["log", f"--since={since}", "--pretty=format:", "--name-only"], repo_path)
    changed_files = {line.strip() for line in output.strip().splitlines() if line.strip()}

    if not changed_files:
        return 0.0

    code_changed = any(f for f in changed_files if f.endswith((".py", ".ts", ".tsx", ".js", ".jsx")))
    if not code_changed:
        return 0.0

    # List all tracked doc files
    all_files_output = _run_git(["ls-files"], repo_path)
    all_files = [line.strip() for line in all_files_output.strip().splitlines() if line.strip()]
    doc_files = [f for f in all_files if f.endswith((".md", ".rst", ".txt")) and not f.startswith("node_modules")]

    if not doc_files:
        return 0.0

    stale_docs = [f for f in doc_files if f not in changed_files]
    return len(stale_docs) / len(doc_files)


# --- Entropy computation ---


def shannon_entropy(counts: dict[str, int]) -> float:
    """Compute normalized Shannon entropy of a distribution (0-1 scale)."""
    total = sum(counts.values())
    if total == 0 or len(counts) <= 1:
        return 0.0
    probs = [c / total for c in counts.values()]
    raw = -sum(p * math.log2(p) for p in probs if p > 0)
    max_entropy = math.log2(len(counts))
    if max_entropy == 0:
        return 0.0
    return raw / max_entropy


def churn_dispersion(churn: list[tuple[str, int]], top_n: int = 10) -> float:
    """Measure how concentrated churn is in top files (0=focused, 1=dispersed)."""
    if not churn:
        return 0.0
    total = sum(c for _, c in churn)
    if total == 0:
        return 0.0
    top_total = sum(c for _, c in churn[:top_n])
    concentration = top_total / total
    # Invert: high concentration = low dispersion
    return 1.0 - concentration


# --- Main analysis ---


def analyze_entropy(days: int = 90, repo_path: str | None = None) -> EntropyReport:
    """Run the full entropy analysis and return a report."""
    messages = get_commit_messages(days, repo_path)
    topic_counts: dict[str, int] = defaultdict(int)
    for msg in messages:
        topic = classify_commit(msg)
        topic_counts[topic] += 1

    topic_entropy = shannon_entropy(dict(topic_counts))
    churn = get_file_churn(days, repo_path)
    dispersion = churn_dispersion(churn)
    sa_delta = get_surface_area_delta(days, repo_path)
    todos = count_todos(repo_path)
    staleness = doc_staleness(days, repo_path)

    indicators: list[DriftIndicator] = []
    recommendations: list[str] = []

    # Evaluate topic entropy
    if topic_entropy > 0.85:
        indicators.append(
            DriftIndicator(
                category="topic_spread",
                description="Commits spread evenly across many topic areas — possible lack of focus",
                severity="high",
                score_contribution=25.0,
            )
        )
        recommendations.append("Consider focusing sprints on fewer topic areas to reduce context switching.")
    elif topic_entropy > 0.65:
        indicators.append(
            DriftIndicator(
                category="topic_spread",
                description="Moderate spread across commit topics",
                severity="medium",
                score_contribution=15.0,
            )
        )

    # Evaluate churn dispersion
    if dispersion > 0.7:
        indicators.append(
            DriftIndicator(
                category="churn_dispersion",
                description="File changes are highly dispersed — work touches many unrelated files",
                severity="high",
                score_contribution=20.0,
            )
        )
        recommendations.append(
            "Review if recent work is scattered across too many areas. Consider batching related changes."
        )
    elif dispersion > 0.4:
        indicators.append(
            DriftIndicator(
                category="churn_dispersion",
                description="Moderate file churn dispersion",
                severity="medium",
                score_contribution=10.0,
            )
        )

    # Evaluate surface area growth
    if sa_delta > 20:
        indicators.append(
            DriftIndicator(
                category="surface_area",
                description=f"Net {sa_delta} new files added — expanding project scope",
                severity="high",
                score_contribution=15.0,
            )
        )
        recommendations.append("Significant file growth detected. Ensure new files align with roadmap goals.")
    elif sa_delta > 10:
        indicators.append(
            DriftIndicator(
                category="surface_area",
                description=f"Net {sa_delta} new files added",
                severity="medium",
                score_contribution=8.0,
            )
        )

    # Evaluate TODO accumulation
    if todos > 30:
        indicators.append(
            DriftIndicator(
                category="todo_debt",
                description=f"{todos} TODO/FIXME/HACK markers found — growing tech debt",
                severity="high",
                score_contribution=15.0,
            )
        )
        recommendations.append("Schedule a tech debt sprint to address accumulated TODOs and FIXMEs.")
    elif todos > 15:
        indicators.append(
            DriftIndicator(
                category="todo_debt",
                description=f"{todos} TODO/FIXME markers found",
                severity="medium",
                score_contribution=8.0,
            )
        )

    # Evaluate doc staleness
    if staleness > 0.7:
        indicators.append(
            DriftIndicator(
                category="doc_staleness",
                description=f"{staleness:.0%} of docs not updated alongside code changes",
                severity="high",
                score_contribution=15.0,
            )
        )
        recommendations.append("Documentation is falling behind code changes. Review and update stale docs.")
    elif staleness > 0.4:
        indicators.append(
            DriftIndicator(
                category="doc_staleness",
                description=f"{staleness:.0%} of docs not updated alongside code changes",
                severity="medium",
                score_contribution=8.0,
            )
        )

    overall = min(100.0, sum(ind.score_contribution for ind in indicators))

    if not indicators:
        recommendations.append("Project entropy is low — development appears focused and well-organized.")

    return EntropyReport(
        overall_score=overall,
        commit_topic_entropy=topic_entropy,
        file_churn_dispersion=dispersion,
        surface_area_delta=sa_delta,
        todo_accumulation=todos,
        doc_staleness_ratio=staleness,
        drift_indicators=indicators,
        topic_counts=dict(topic_counts),
        churn_hotspots=churn[:10],
        recommendations=recommendations,
    )
