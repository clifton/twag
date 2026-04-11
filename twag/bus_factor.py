"""Bus-factor analysis using git-blame data."""

from __future__ import annotations

import os
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ModuleStats:
    """Ownership statistics for a single module (file or directory)."""

    path: str
    lines_by_author: dict[str, int] = field(default_factory=dict)

    @property
    def total_lines(self) -> int:
        return sum(self.lines_by_author.values())

    @property
    def dominant_author(self) -> str | None:
        if not self.lines_by_author:
            return None
        return max(self.lines_by_author, key=lambda a: self.lines_by_author[a])

    @property
    def dominant_ownership_pct(self) -> float:
        total = self.total_lines
        if total == 0:
            return 0.0
        return self.lines_by_author.get(self.dominant_author or "", 0) / total * 100

    @property
    def bus_factor(self) -> int:
        """Minimum number of authors whose departure loses >50% of lines."""
        total = self.total_lines
        if total == 0:
            return 0
        sorted_authors = sorted(self.lines_by_author.values(), reverse=True)
        cumulative = 0
        threshold = total * 0.5
        for i, lines in enumerate(sorted_authors):
            cumulative += lines
            if cumulative > threshold:
                return i + 1
        return len(sorted_authors)

    @property
    def risk_level(self) -> str:
        bf = self.bus_factor
        if bf == 0:
            return "N/A"
        if bf == 1:
            return "CRITICAL"
        if bf == 2:
            return "HIGH"
        if bf <= 3:
            return "MEDIUM"
        return "LOW"


def parse_git_blame_porcelain(output: str) -> dict[str, int]:
    """Parse git blame --porcelain output into {author: line_count}."""
    counts: dict[str, int] = defaultdict(int)
    for line in output.splitlines():
        if line.startswith("author "):
            author = line[7:]
            counts[author] += 1
    return dict(counts)


def get_tracked_files(repo_path: str, extensions: list[str] | None = None) -> list[str]:
    """List git-tracked files, optionally filtered by extension."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    files = [f for f in result.stdout.splitlines() if f]
    if extensions:
        ext_set = {ext if ext.startswith(".") else f".{ext}" for ext in extensions}
        files = [f for f in files if os.path.splitext(f)[1] in ext_set]
    return files


def blame_file(repo_path: str, filepath: str) -> dict[str, int]:
    """Run git blame on a single file and return author line counts."""
    try:
        result = subprocess.run(
            ["git", "blame", "--porcelain", filepath],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return {}
    return parse_git_blame_porcelain(result.stdout)


def aggregate_ownership(
    file_stats: dict[str, dict[str, int]],
) -> dict[str, ModuleStats]:
    """Aggregate per-file ownership into per-directory ModuleStats.

    Returns a dict mapping directory path -> ModuleStats. Each file's
    ownership is also available as its own ModuleStats entry.
    """
    dir_ownership: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    result: dict[str, ModuleStats] = {}

    for filepath, author_lines in file_stats.items():
        # Per-file stats
        result[filepath] = ModuleStats(path=filepath, lines_by_author=dict(author_lines))

        # Accumulate into parent directory
        parent = str(Path(filepath).parent)
        if parent == ".":
            parent = "(root)"
        for author, lines in author_lines.items():
            dir_ownership[parent][author] += lines

    for dirpath, authors in dir_ownership.items():
        result[dirpath] = ModuleStats(path=dirpath, lines_by_author=dict(authors))

    return result


def compute_repo_bus_factor(file_stats: dict[str, dict[str, int]]) -> ModuleStats:
    """Compute a single repo-wide ModuleStats from all file data."""
    total: dict[str, int] = defaultdict(int)
    for author_lines in file_stats.values():
        for author, lines in author_lines.items():
            total[author] += lines
    return ModuleStats(path="(repo)", lines_by_author=dict(total))


def analyze_repo(
    path: str = ".",
    extensions: list[str] | None = None,
) -> tuple[ModuleStats, dict[str, ModuleStats]]:
    """Full analysis: returns (repo_stats, per_module_stats)."""
    files = get_tracked_files(path, extensions)
    file_stats: dict[str, dict[str, int]] = {}
    for f in files:
        ownership = blame_file(path, f)
        if ownership:
            file_stats[f] = ownership

    repo_stats = compute_repo_bus_factor(file_stats)
    module_stats = aggregate_ownership(file_stats)
    return repo_stats, module_stats
