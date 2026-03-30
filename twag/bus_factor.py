"""Bus-factor analysis using git-blame data.

Measures code ownership concentration per module and repo-wide.
The bus factor is the minimum number of authors who must leave before
>50% of a module's lines are unowned.
"""

from __future__ import annotations

import os
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ModuleStats:
    """Ownership statistics for a single module (directory or file)."""

    path: str
    total_lines: int = 0
    author_lines: dict[str, int] = field(default_factory=dict)

    @property
    def bus_factor(self) -> int:
        """Minimum authors whose departure loses >50% of lines."""
        if self.total_lines == 0:
            return 0
        sorted_authors = sorted(self.author_lines.values(), reverse=True)
        threshold = self.total_lines * 0.5
        cumulative = 0
        for i, lines in enumerate(sorted_authors, 1):
            cumulative += lines
            if cumulative > threshold:
                return i
        return len(sorted_authors)

    @property
    def dominant_author(self) -> tuple[str, float]:
        """Return (author, percentage) of the top contributor."""
        if not self.author_lines or self.total_lines == 0:
            return ("", 0.0)
        top = max(self.author_lines, key=lambda a: self.author_lines[a])
        pct = self.author_lines[top] / self.total_lines * 100
        return (top, pct)

    @property
    def risk_level(self) -> str:
        """Risk classification based on bus factor."""
        bf = self.bus_factor
        if bf <= 1:
            return "HIGH"
        if bf <= 2:
            return "MEDIUM"
        return "LOW"


def parse_git_blame_porcelain(output: str) -> list[tuple[str, int]]:
    """Parse git blame --line-porcelain output into (author, line_count) pairs.

    Returns a list of (author, 1) tuples — one per blamed line.
    """
    results: list[tuple[str, int]] = []
    current_author: str | None = None
    for line in output.splitlines():
        if line.startswith("author "):
            current_author = line[7:].strip()
        elif line.startswith("\t") and current_author is not None:
            results.append((current_author, 1))
            current_author = None
    return results


def get_tracked_files(repo_path: str | Path) -> list[str]:
    """Get list of tracked files from git."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return [f for f in result.stdout.strip().splitlines() if f]


def blame_file(repo_path: str | Path, filepath: str) -> list[tuple[str, int]]:
    """Run git blame on a single file and return (author, 1) pairs."""
    try:
        result = subprocess.run(
            ["git", "blame", "--line-porcelain", filepath],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return []
    return parse_git_blame_porcelain(result.stdout)


def aggregate_ownership(
    blame_data: dict[str, list[tuple[str, int]]],
) -> dict[str, ModuleStats]:
    """Aggregate blame data into per-module ownership stats.

    blame_data: mapping of filepath -> list of (author, line_count) pairs
    Returns: mapping of module_path -> ModuleStats
    """
    modules: dict[str, ModuleStats] = {}

    # Per-file stats
    for filepath, entries in blame_data.items():
        file_stats = ModuleStats(path=filepath)
        for author, count in entries:
            file_stats.author_lines[author] = file_stats.author_lines.get(author, 0) + count
            file_stats.total_lines += count
        if file_stats.total_lines > 0:
            modules[filepath] = file_stats

    # Per-directory (module) stats
    dir_data: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    dir_totals: dict[str, int] = defaultdict(int)

    for filepath, entries in blame_data.items():
        parts = filepath.split("/")
        for depth in range(1, len(parts)):
            dir_path = "/".join(parts[:depth])
            for author, count in entries:
                dir_data[dir_path][author] += count
                dir_totals[dir_path] += count

    for dir_path, author_lines in dir_data.items():
        stats = ModuleStats(
            path=dir_path + "/",
            total_lines=dir_totals[dir_path],
            author_lines=dict(author_lines),
        )
        modules[dir_path + "/"] = stats

    return modules


def compute_repo_bus_factor(modules: dict[str, ModuleStats]) -> int:
    """Compute repo-wide bus factor: min bus factor across top-level modules."""
    top_level = [s for p, s in modules.items() if p.endswith("/") and p.count("/") == 1]
    if not top_level:
        top_level = [s for s in modules.values() if "/" not in s.path]
    if not top_level:
        return 0
    return min(s.bus_factor for s in top_level)


def analyze_repo(
    repo_path: str | Path | None = None,
    extensions: set[str] | None = None,
) -> tuple[dict[str, ModuleStats], int]:
    """Run full bus-factor analysis on a git repository.

    Args:
        repo_path: Path to git repo (defaults to cwd).
        extensions: If set, only analyze files with these extensions (e.g. {'.py', '.js'}).

    Returns:
        (modules dict, repo_bus_factor)
    """
    if repo_path is None:
        repo_path = os.getcwd()
    repo_path = Path(repo_path)

    files = get_tracked_files(repo_path)
    if extensions:
        files = [f for f in files if Path(f).suffix in extensions]

    blame_data: dict[str, list[tuple[str, int]]] = {}
    for filepath in files:
        entries = blame_file(repo_path, filepath)
        if entries:
            blame_data[filepath] = entries

    modules = aggregate_ownership(blame_data)
    repo_bf = compute_repo_bus_factor(modules)
    return modules, repo_bf
