#!/usr/bin/env python3
"""Roadmap entropy detector — quantify scope creep and drift from declared priorities.

Parses ROADMAP.md for declared work themes, analyzes recent git history,
and classifies commits as aligned or unplanned. Outputs entropy metrics
as a Rich CLI report or JSON.

Usage:
    python scripts/roadmap_entropy.py [--json] [--days N] [--roadmap PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# ROADMAP parsing
# ---------------------------------------------------------------------------

THEME_HEADER_RE = re.compile(r"^###\s+(.+)$")


def parse_roadmap(text: str) -> list[str]:
    """Extract theme names from ROADMAP.md content.

    Themes are identified as ### headings under a ## Themes section.
    Returns lowercased theme slugs.
    """
    themes: list[str] = []
    in_themes = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and "theme" in stripped.lower():
            in_themes = True
            continue
        if stripped.startswith("## ") and in_themes:
            break
        if in_themes:
            m = THEME_HEADER_RE.match(stripped)
            if m:
                themes.append(m.group(1).strip().lower())
    return themes


def build_keywords(themes: list[str]) -> dict[str, list[str]]:
    """Derive match keywords from theme slugs.

    Splits hyphenated theme names into individual keywords for fuzzy matching
    against commit subjects and changed file paths.
    """
    kw: dict[str, list[str]] = {}
    for t in themes:
        parts = re.split(r"[-_/\s]+", t)
        kw[t] = [p for p in parts if len(p) > 2]
    return kw


# ---------------------------------------------------------------------------
# Git log
# ---------------------------------------------------------------------------


@dataclass
class CommitInfo:
    sha: str
    subject: str
    files: list[str] = field(default_factory=list)


# Path mapping: map top-level directory or file to a likely theme.
PATH_THEME_MAP: dict[str, str] = {
    "twag/fetcher": "pipeline-reliability",
    "twag/processor": "pipeline-reliability",
    "twag/scorer": "scoring-quality",
    "twag/web": "web-feed",
    "twag/cli": "cli-ux",
    "twag/db": "data-integrity",
    "twag/notifier": "ops-automation",
    "twag/renderer": "web-feed",
    "twag/link_utils": "data-integrity",
    "twag/article": "scoring-quality",
    "scripts": "ops-automation",
    "ROADMAP.md": "docs",
    "README.md": "docs",
    "SKILL.md": "docs",
    "CLAUDE.md": "docs",
    "INSTALL.md": "docs",
    "TELEGRAM_DIGEST_FORMAT.md": "docs",
    "tests": "lint-quality",
    "pyproject.toml": "ops-automation",
    ".github": "ops-automation",
}


def get_git_log(days: int = 30, repo: str | None = None) -> list[CommitInfo]:
    """Read git log for the last *days* days, returning commits with changed files."""
    cmd = [
        "git",
        "log",
        f"--since={days} days ago",
        "--pretty=format:%H%x00%s",
        "--name-only",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=repo,
        check=True,
    )
    commits: list[CommitInfo] = []
    current: CommitInfo | None = None
    for line in result.stdout.splitlines():
        if "\x00" in line:
            parts = line.split("\x00", 1)
            current = CommitInfo(sha=parts[0], subject=parts[1])
            commits.append(current)
        elif line.strip() and current is not None:
            current.files.append(line.strip())
    return commits


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_commit(commit: CommitInfo, themes: list[str], keywords: dict[str, list[str]]) -> str | None:
    """Return the best-matching theme for a commit, or None if unplanned."""
    subject_lower = commit.subject.lower()

    # 1. Exact theme slug in subject
    for t in themes:
        if t in subject_lower:
            return t

    # 2. Keyword match in subject
    best: str | None = None
    best_score = 0
    for t, kws in keywords.items():
        score = sum(1 for k in kws if k in subject_lower)
        if score > best_score:
            best_score = score
            best = t
    if best_score >= 1:
        return best

    # 3. Path-based heuristic
    theme_votes: dict[str, int] = {}
    for f in commit.files:
        for prefix, theme in PATH_THEME_MAP.items():
            if f.startswith(prefix):
                theme_votes[theme] = theme_votes.get(theme, 0) + 1
                break
    if theme_votes:
        return max(theme_votes, key=lambda k: theme_votes[k])

    return None


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@dataclass
class EntropyReport:
    total_commits: int
    aligned_commits: int
    unplanned_commits: int
    unplanned_ratio: float
    directory_spread: float
    new_file_rate: float
    drift_score: float
    theme_counts: dict[str, int]
    unplanned_subjects: list[str]


def compute_metrics(
    commits: list[CommitInfo],
    themes: list[str],
    keywords: dict[str, list[str]],
) -> EntropyReport:
    """Compute entropy metrics from classified commits."""
    if not commits:
        return EntropyReport(
            total_commits=0,
            aligned_commits=0,
            unplanned_commits=0,
            unplanned_ratio=0.0,
            directory_spread=0.0,
            new_file_rate=0.0,
            drift_score=0.0,
            theme_counts={},
            unplanned_subjects=[],
        )

    theme_counts: dict[str, int] = {t: 0 for t in themes}
    unplanned_subjects: list[str] = []
    aligned = 0
    total_dirs: set[str] = set()
    total_files = 0
    new_files = 0

    for c in commits:
        match = classify_commit(c, themes, keywords)
        if match:
            aligned += 1
            theme_counts[match] = theme_counts.get(match, 0) + 1
        else:
            unplanned_subjects.append(c.subject)

        for f in c.files:
            total_files += 1
            parts = f.split("/")
            total_dirs.add(parts[0] if len(parts) > 1 else ".")

    # New-file rate: files added that don't appear in earlier commits
    # Approximation: count unique files across all commits vs total mentions
    all_files: set[str] = set()
    for c in commits:
        for f in c.files:
            if f not in all_files:
                new_files += 1
            all_files.add(f)

    n = len(commits)
    unplanned = n - aligned
    unplanned_ratio = unplanned / n
    dir_spread = len(total_dirs) / n if n else 0.0
    new_rate = new_files / total_files if total_files else 0.0

    # Composite drift score: weighted blend [0, 1]
    drift_score = min(1.0, 0.5 * unplanned_ratio + 0.3 * min(dir_spread, 1.0) + 0.2 * new_rate)

    return EntropyReport(
        total_commits=n,
        aligned_commits=aligned,
        unplanned_commits=unplanned,
        unplanned_ratio=round(unplanned_ratio, 3),
        directory_spread=round(dir_spread, 3),
        new_file_rate=round(new_rate, 3),
        drift_score=round(drift_score, 3),
        theme_counts=theme_counts,
        unplanned_subjects=unplanned_subjects,
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_json(report: EntropyReport) -> None:
    from dataclasses import asdict

    print(json.dumps(asdict(report), indent=2))


def print_rich(report: EntropyReport) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print()
    console.rule("[bold]Roadmap Entropy Report[/bold]")
    console.print()

    # Summary metrics
    summary = Table(title="Metrics", show_header=False, box=None)
    summary.add_column(style="bold")
    summary.add_column(justify="right")
    summary.add_row("Total commits", str(report.total_commits))
    summary.add_row("Aligned", str(report.aligned_commits))
    summary.add_row("Unplanned", str(report.unplanned_commits))
    summary.add_row("Unplanned ratio", f"{report.unplanned_ratio:.1%}")
    summary.add_row("Directory spread", f"{report.directory_spread:.2f}")
    summary.add_row("New-file rate", f"{report.new_file_rate:.1%}")

    drift_color = "green" if report.drift_score < 0.3 else "yellow" if report.drift_score < 0.6 else "red"
    summary.add_row("Drift score", f"[{drift_color}]{report.drift_score:.3f}[/{drift_color}]")
    console.print(summary)
    console.print()

    # Theme breakdown
    if report.theme_counts:
        theme_table = Table(title="Theme Breakdown")
        theme_table.add_column("Theme")
        theme_table.add_column("Commits", justify="right")
        for theme, count in sorted(report.theme_counts.items(), key=lambda x: -x[1]):
            if count > 0:
                theme_table.add_row(theme, str(count))
        console.print(theme_table)
        console.print()

    # Unplanned commits
    if report.unplanned_subjects:
        console.print("[bold red]Unplanned commits:[/bold red]")
        for s in report.unplanned_subjects:
            console.print(f"  • {s}")
        console.print()


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Roadmap entropy detector")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of Rich table")
    parser.add_argument("--days", type=int, default=30, help="Number of days to analyze (default: 30)")
    parser.add_argument("--roadmap", type=str, default=None, help="Path to ROADMAP.md")
    args = parser.parse_args(argv)

    roadmap_path = Path(args.roadmap) if args.roadmap else Path(__file__).resolve().parent.parent / "ROADMAP.md"
    if not roadmap_path.exists():
        print(f"Error: {roadmap_path} not found", file=sys.stderr)
        sys.exit(1)

    themes = parse_roadmap(roadmap_path.read_text())
    if not themes:
        print("Error: no themes found in ROADMAP.md", file=sys.stderr)
        sys.exit(1)

    keywords = build_keywords(themes)
    commits = get_git_log(days=args.days, repo=str(roadmap_path.parent))
    report = compute_metrics(commits, themes, keywords)

    if args.json:
        print_json(report)
    else:
        print_rich(report)


if __name__ == "__main__":
    main()
