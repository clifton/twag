#!/usr/bin/env python3
"""Detect roadmap scope creep and architectural drift from git history.

Analyzes commit patterns over weekly time windows to surface:
- Subsystem spread per window (how many packages each commit touches)
- New file/module introduction rate
- Dependency growth in pyproject.toml
- Commit message topic drift via keyword clustering
- File churn concentration (Gini coefficient across packages)

Outputs a JSON report. Uses only stdlib — no external dependencies.

Usage:
    python scripts/roadmap_entropy.py [--weeks N] [--repo-path PATH] [--output PATH]
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import math
import pathlib
import re
import subprocess
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def git_log(repo: pathlib.Path, since: str, until: str) -> list[dict[str, Any]]:
    """Return commits in [since, until) with hash, date, subject, and changed files."""
    sep = "---COMMIT---"
    fmt = f"%H%n%aI%n%s%n{sep}"
    cmd = [
        "git",
        "-C",
        str(repo),
        "log",
        f"--since={since}",
        f"--until={until}",
        "--no-merges",
        f"--pretty=format:{fmt}",
        "--name-only",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    raw = result.stdout.strip()
    if not raw:
        return []

    commits: list[dict[str, Any]] = []
    blocks = raw.split(sep)
    for block in blocks:
        lines = [line for line in block.strip().splitlines() if line]
        if len(lines) < 3:
            continue
        sha, date_str, subject = lines[0], lines[1], lines[2]
        files = lines[3:]
        commits.append(
            {
                "sha": sha,
                "date": date_str,
                "subject": subject,
                "files": files,
            },
        )
    return commits


def git_diff_deps(repo: pathlib.Path, since: str, until: str) -> dict[str, int]:
    """Count net dependency additions in pyproject.toml over a window."""
    cmd_before = [
        "git",
        "-C",
        str(repo),
        "log",
        f"--since={since}",
        f"--until={until}",
        "--diff-filter=M",
        "--pretty=format:",
        "-p",
        "--",
        "pyproject.toml",
    ]
    result = subprocess.run(cmd_before, capture_output=True, text=True, check=True)
    patch = result.stdout
    added = 0
    removed = 0
    dep_re = re.compile(r'^[+-]\s*"[a-zA-Z]')
    in_deps = False
    for line in patch.splitlines():
        if "dependencies" in line.lower():
            in_deps = True
            continue
        if in_deps and line.startswith("@@"):
            in_deps = False
        if in_deps and dep_re.match(line):
            if line.startswith("+"):
                added += 1
            elif line.startswith("-"):
                removed += 1
    return {"deps_added": added, "deps_removed": removed, "deps_net": added - removed}


# ---------------------------------------------------------------------------
# Pure-logic analysis functions
# ---------------------------------------------------------------------------

SUBSYSTEMS = [
    "twag/cli",
    "twag/db",
    "twag/fetcher",
    "twag/processor",
    "twag/scorer",
    "twag/web",
    "twag/models",
]
TOP_LEVEL_MODULES = [
    "twag/auth.py",
    "twag/config.py",
    "twag/notifier.py",
    "twag/renderer.py",
    "twag/tables.py",
    "twag/media.py",
    "twag/link_utils.py",
    "twag/text_utils.py",
    "twag/metrics.py",
    "twag/article_visuals.py",
    "twag/article_sections.py",
]


def classify_file(path: str) -> str | None:
    """Map a file path to a subsystem name, or None if outside twag/."""
    for sub in SUBSYSTEMS:
        if path.startswith(sub + "/") or path == sub:
            return sub
    for mod in TOP_LEVEL_MODULES:
        if path == mod:
            return mod
    if path.startswith("twag/"):
        return "twag/other"
    if path.startswith("tests/"):
        return "tests"
    if path.startswith("scripts/"):
        return "scripts"
    return "root"


def subsystem_spread(commits: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute per-commit subsystem spread and aggregate stats."""
    spreads: list[int] = []
    subsystem_counts: dict[str, int] = collections.Counter()
    for c in commits:
        touched = set()
        for f in c["files"]:
            sub = classify_file(f)
            if sub:
                touched.add(sub)
                subsystem_counts[sub] += 1
        spreads.append(len(touched))
    avg = sum(spreads) / len(spreads) if spreads else 0.0
    return {
        "avg_subsystems_per_commit": round(avg, 2),
        "max_subsystems_in_commit": max(spreads) if spreads else 0,
        "subsystem_touch_counts": dict(subsystem_counts.most_common()),
    }


def new_files(commits: list[dict[str, Any]], known_files: set[str]) -> list[str]:
    """Identify files that appear for the first time in this window."""
    introduced: list[str] = []
    for c in commits:
        for f in c["files"]:
            if f not in known_files:
                introduced.append(f)
                known_files.add(f)
    return introduced


def gini_coefficient(values: list[int]) -> float:
    """Compute the Gini coefficient of a list of non-negative integers."""
    if not values or all(v == 0 for v in values):
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    numerator = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(sorted_vals))
    return numerator / (n * total)


def churn_concentration(commits: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute file churn Gini across subsystems."""
    counts: dict[str, int] = collections.Counter()
    for c in commits:
        for f in c["files"]:
            sub = classify_file(f)
            if sub:
                counts[sub] += 1
    values = list(counts.values())
    gini = gini_coefficient(values)
    return {
        "gini": round(gini, 3),
        "churn_by_subsystem": dict(counts.most_common()),
    }


TOPIC_KEYWORDS: dict[str, list[str]] = {
    "feat": ["add", "feature", "implement", "new", "introduce", "support"],
    "fix": ["fix", "bug", "patch", "repair", "resolve", "hotfix"],
    "refactor": ["refactor", "clean", "reorganize", "simplify", "restructure"],
    "test": ["test", "spec", "coverage", "assert"],
    "docs": ["doc", "readme", "guide", "comment"],
    "infra": ["ci", "deploy", "docker", "build", "pipeline", "cron", "config"],
    "deps": ["dependency", "upgrade", "bump", "migrate", "update"],
}


def classify_commit_topic(subject: str) -> str:
    """Classify a commit message into a topic bucket."""
    lower = subject.lower()
    scores: dict[str, int] = collections.Counter()
    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                scores[topic] += 1
    if scores:
        return scores.most_common(1)[0][0]
    return "other"


def topic_distribution(commits: list[dict[str, Any]]) -> dict[str, int]:
    """Return topic → count mapping for a set of commits."""
    dist: dict[str, int] = collections.Counter()
    for c in commits:
        topic = classify_commit_topic(c["subject"])
        dist[topic] += 1
    return dict(dist.most_common())


def shannon_entropy(distribution: dict[str, int]) -> float:
    """Compute Shannon entropy of a distribution (in bits)."""
    total = sum(distribution.values())
    if total == 0:
        return 0.0
    ent = 0.0
    for count in distribution.values():
        if count > 0:
            p = count / total
            ent -= p * math.log2(p)
    return round(ent, 3)


def detect_anomalies(
    window_label: str,
    spread: dict[str, Any],
    new_file_count: int,
    dep_info: dict[str, int],
    churn: dict[str, Any],
    topic_entropy: float,
    total_subsystems: int,
) -> list[str]:
    """Flag anomalies for a time window."""
    flags: list[str] = []
    touched = len(spread.get("subsystem_touch_counts", {}))
    if total_subsystems > 0 and touched / total_subsystems > 0.7:
        flags.append(f"{window_label}: commits touched {touched}/{total_subsystems} subsystems")
    if new_file_count >= 4:
        flags.append(f"{window_label}: {new_file_count} new files introduced")
    if dep_info.get("deps_net", 0) >= 3:
        flags.append(f"{window_label}: {dep_info['deps_net']} net new dependencies")
    if spread.get("avg_subsystems_per_commit", 0) > 3:
        flags.append(f"{window_label}: avg subsystem spread {spread['avg_subsystems_per_commit']} per commit")
    if topic_entropy > 2.5:
        flags.append(f"{window_label}: high topic entropy ({topic_entropy} bits) — scattered focus")
    if churn.get("gini", 0) > 0.7:
        flags.append(f"{window_label}: high churn concentration (Gini {churn['gini']})")
    return flags


# ---------------------------------------------------------------------------
# Window bucketing
# ---------------------------------------------------------------------------


def week_boundaries(weeks: int) -> list[tuple[str, str, str]]:
    """Return (label, since_iso, until_iso) for the last N weeks ending today."""
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    boundaries: list[tuple[str, str, str]] = []
    for i in range(weeks):
        end = monday - datetime.timedelta(weeks=i)
        start = end - datetime.timedelta(weeks=1)
        label = f"week of {start.isoformat()}"
        boundaries.append((label, start.isoformat(), end.isoformat()))
    boundaries.reverse()
    return boundaries


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def analyze_repo(repo: pathlib.Path, weeks: int) -> dict[str, Any]:
    """Run full analysis and return a JSON-serializable report."""
    windows = week_boundaries(weeks)
    total_subsystems = len(SUBSYSTEMS) + len(TOP_LEVEL_MODULES)
    known_files: set[str] = set()
    window_reports: list[dict[str, Any]] = []
    all_anomalies: list[str] = []
    overall_topics: dict[str, int] = collections.Counter()

    for label, since, until in windows:
        commits = git_log(repo, since, until)
        if not commits:
            window_reports.append({"window": label, "commits": 0, "skipped": True})
            continue

        spread = subsystem_spread(commits)
        introduced = new_files(commits, known_files)
        dep_info = git_diff_deps(repo, since, until)
        churn = churn_concentration(commits)
        topics = topic_distribution(commits)
        t_entropy = shannon_entropy(topics)

        for topic, count in topics.items():
            overall_topics[topic] += count

        anomalies = detect_anomalies(
            label,
            spread,
            len(introduced),
            dep_info,
            churn,
            t_entropy,
            total_subsystems,
        )
        all_anomalies.extend(anomalies)

        window_reports.append(
            {
                "window": label,
                "commits": len(commits),
                "subsystem_spread": spread,
                "new_files": len(introduced),
                "new_file_paths": introduced[:20],
                "dependency_changes": dep_info,
                "churn_concentration": churn,
                "topic_distribution": topics,
                "topic_entropy_bits": t_entropy,
                "anomalies": anomalies,
            },
        )

    overall_entropy = shannon_entropy(dict(overall_topics))
    return {
        "repo": str(repo),
        "weeks_analyzed": weeks,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "overall_topic_entropy_bits": overall_entropy,
        "total_anomalies": len(all_anomalies),
        "anomalies": all_anomalies,
        "windows": window_reports,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect roadmap scope creep and architectural drift from git history.",
    )
    parser.add_argument("--weeks", type=int, default=8, help="Number of weeks to analyze (default: 8)")
    parser.add_argument("--repo-path", type=str, default=".", help="Path to git repository")
    parser.add_argument("--output", type=str, default=None, help="Output file (default: stdout)")
    args = parser.parse_args()

    repo = pathlib.Path(args.repo_path).resolve()
    report = analyze_repo(repo, args.weeks)
    output = json.dumps(report, indent=2)

    if args.output:
        pathlib.Path(args.output).write_text(output + "\n")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
