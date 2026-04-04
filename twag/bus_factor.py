"""Git-blame-based bus factor analysis.

Computes per-file and per-directory code ownership concentration.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field


@dataclass
class FileOwnership:
    path: str
    total_lines: int = 0
    authors: dict[str, int] = field(default_factory=dict)

    @property
    def top_author_pct(self) -> float:
        if not self.total_lines:
            return 0.0
        return max(self.authors.values(), default=0) / self.total_lines * 100


def git_tracked_files(repo_dir: str) -> list[str]:
    """Return list of tracked files in the repo."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return [f for f in result.stdout.strip().splitlines() if f]


def blame_file(repo_dir: str, filepath: str) -> dict[str, int]:
    """Run git blame on a file and return {author: line_count}.

    Returns empty dict for binary files or files that git blame cannot process.
    """
    result = subprocess.run(
        ["git", "blame", "--line-porcelain", filepath],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}

    authors: dict[str, int] = {}
    for line in result.stdout.splitlines():
        if line.startswith("author "):
            name = line[7:]
            authors[name] = authors.get(name, 0) + 1
    return authors


def analyze_repo(repo_dir: str) -> dict:
    """Analyze bus factor for the entire repository.

    Returns a structured dict with overall stats, per-directory breakdown,
    high-risk modules, and file-level detail.
    """
    files = git_tracked_files(repo_dir)
    file_ownerships: list[FileOwnership] = []

    for filepath in files:
        authors = blame_file(repo_dir, filepath)
        if not authors:
            continue
        fo = FileOwnership(
            path=filepath,
            total_lines=sum(authors.values()),
            authors=authors,
        )
        file_ownerships.append(fo)

    # Aggregate repo-level ownership
    repo_authors: dict[str, int] = {}
    total_lines = 0
    for fo in file_ownerships:
        for author, count in fo.authors.items():
            repo_authors[author] = repo_authors.get(author, 0) + count
        total_lines += fo.total_lines

    # Compute bus factor: minimum authors covering >50% of lines
    bus_factor = _compute_bus_factor(repo_authors, total_lines)

    # Per-directory aggregation
    dir_ownership: dict[str, dict[str, int]] = {}
    dir_lines: dict[str, int] = {}
    for fo in file_ownerships:
        d = os.path.dirname(fo.path) or "."
        if d not in dir_ownership:
            dir_ownership[d] = {}
            dir_lines[d] = 0
        dir_lines[d] += fo.total_lines
        for author, count in fo.authors.items():
            dir_ownership[d][author] = dir_ownership[d].get(author, 0) + count

    directories = {}
    for d in sorted(dir_ownership):
        authors_sorted = sorted(dir_ownership[d].items(), key=lambda x: x[1], reverse=True)
        top_pct = (authors_sorted[0][1] / dir_lines[d] * 100) if authors_sorted else 0
        directories[d] = {
            "total_lines": dir_lines[d],
            "authors": {a: c for a, c in authors_sorted},
            "top_author": authors_sorted[0][0] if authors_sorted else None,
            "top_author_pct": round(top_pct, 1),
        }

    # High-risk modules: single author owns >75% of lines
    high_risk = []
    for fo in file_ownerships:
        if fo.top_author_pct > 75 and fo.total_lines >= 10:
            top = max(fo.authors, key=lambda a: fo.authors[a])
            high_risk.append(
                {
                    "path": fo.path,
                    "total_lines": fo.total_lines,
                    "top_author": top,
                    "top_author_pct": round(fo.top_author_pct, 1),
                }
            )
    high_risk.sort(key=lambda x: x["total_lines"], reverse=True)

    # File-level detail
    file_detail = [
        {
            "path": fo.path,
            "total_lines": fo.total_lines,
            "authors": fo.authors,
        }
        for fo in sorted(file_ownerships, key=lambda f: f.total_lines, reverse=True)
    ]

    authors_sorted = sorted(repo_authors.items(), key=lambda x: x[1], reverse=True)

    return {
        "bus_factor": bus_factor,
        "total_lines": total_lines,
        "total_files": len(file_ownerships),
        "unique_authors": len(repo_authors),
        "authors": {a: c for a, c in authors_sorted},
        "directories": directories,
        "high_risk_files": high_risk,
        "files": file_detail,
    }


def _compute_bus_factor(authors: dict[str, int], total_lines: int) -> int:
    """Minimum number of authors whose lines cover >50% of total."""
    if total_lines == 0:
        return 0
    sorted_counts = sorted(authors.values(), reverse=True)
    cumulative = 0
    for i, count in enumerate(sorted_counts, 1):
        cumulative += count
        if cumulative > total_lines * 0.5:
            return i
    return len(sorted_counts)


def format_report_json(report: dict) -> str:
    """Format the report as indented JSON."""
    return json.dumps(report, indent=2)
