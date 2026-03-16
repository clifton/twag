#!/usr/bin/env python3
"""Identify knowledge silos in the repository by analyzing git history.

Produces a JSON report showing:
- Contributor count and commit distribution
- Per-directory ownership concentration (bus factor)
- Files touched by only one author
- Recommendations for knowledge sharing
"""

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_contributors() -> dict[str, int]:
    """Return {normalized_name: commit_count}."""
    log = run_git("log", "--all", "--format=%an")
    counts: dict[str, int] = defaultdict(int)
    for name in log.splitlines():
        counts[name.strip()] += 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def get_file_authors() -> dict[str, set[str]]:
    """Map each file ever in git history to the set of authors who touched it."""
    log = run_git("log", "--all", "--numstat", "--format=COMMIT:%an")
    file_authors: dict[str, set[str]] = defaultdict(set)
    current_author = None
    for line in log.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("COMMIT:"):
            current_author = line[7:]
            continue
        parts = line.split("\t")
        if len(parts) == 3 and current_author:
            filepath = parts[2]
            # Skip binary diffs (shown as -)
            if parts[0] != "-":
                file_authors[filepath].add(current_author)
    return file_authors


def directory_bus_factor(file_authors: dict[str, set[str]], depth: int = 1) -> list[dict]:
    """Compute bus factor per top-level directory.

    Bus factor = number of distinct authors who have touched files in that directory.
    """
    dir_authors: dict[str, set[str]] = defaultdict(set)
    dir_files: dict[str, int] = defaultdict(int)

    for filepath, authors in file_authors.items():
        parts = Path(filepath).parts
        if len(parts) > depth:
            directory = str(Path(*parts[:depth]))
        else:
            directory = "(root)"
        dir_authors[directory].update(authors)
        dir_files[directory] += 1

    results = [
        {
            "directory": directory,
            "bus_factor": len(dir_authors[directory]),
            "authors": sorted(dir_authors[directory]),
            "file_count": dir_files[directory],
        }
        for directory in sorted(dir_authors)
    ]
    return sorted(results, key=lambda x: x["bus_factor"])


def sole_author_files(
    file_authors: dict[str, set[str]],
) -> list[dict]:
    """Files with exactly one author, grouped by directory."""
    existing = {str(p) for p in Path(".").rglob("*") if p.is_file()}
    sole = {}
    for filepath, authors in file_authors.items():
        if len(authors) == 1 and filepath in existing:
            author = next(iter(authors))
            if author not in sole:
                sole[author] = []
            sole[author].append(filepath)

    return [
        {"author": author, "file_count": len(files), "files": sorted(files)}
        for author, files in sorted(sole.items(), key=lambda x: -len(x[1]))
    ]


def build_report() -> dict:
    contributors = get_contributors()
    file_authors = get_file_authors()

    total_files = sum(1 for f in file_authors if Path(f).exists())
    single_author_count = sum(1 for f, a in file_authors.items() if len(a) == 1 and Path(f).exists())

    bus = directory_bus_factor(file_authors)
    sole = sole_author_files(file_authors)

    # Build recommendations
    recommendations = []
    if len(contributors) == 1:
        recommendations.append(
            "CRITICAL: Single contributor — entire codebase is a knowledge silo. "
            "All institutional knowledge depends on one person."
        )
    silos = [d for d in bus if d["bus_factor"] == 1 and d["file_count"] >= 3]
    if silos and len(contributors) > 1:
        dirs = [s["directory"] for s in silos]
        recommendations.append(
            f"Directories with bus factor 1 (knowledge silos): {', '.join(dirs)}. "
            "Consider pair programming or code review rotation for these areas."
        )
    if total_files > 0 and single_author_count / total_files > 0.8:
        pct = round(100 * single_author_count / total_files)
        recommendations.append(
            f"{pct}% of existing files have been touched by only one author. Broad cross-pollination is needed."
        )

    return {
        "summary": {
            "total_contributors": len(contributors),
            "total_files_in_history": len(file_authors),
            "existing_files_with_single_author": single_author_count,
            "existing_files_total": total_files,
        },
        "contributors": contributors,
        "directory_bus_factor": bus,
        "sole_author_files": sole,
        "recommendations": recommendations,
    }


def main() -> None:
    report = build_report()
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
