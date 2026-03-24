#!/usr/bin/env python3
"""Bus-factor analyzer — measures per-file and per-module code ownership concentration.

Uses git-blame to attribute lines to authors, then computes ownership percentages
and a bus-factor score (number of authors who collectively own >50% of the code).

Usage:
    python scripts/bus_factor.py [--repo-root DIR] [--output FILE] [--format json|markdown]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def get_tracked_files(repo_root: Path) -> list[str]:
    """Return list of tracked files suitable for blame analysis."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    skip_extensions = {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2",
        ".ttf", ".eot", ".lock", ".pyc", ".map", ".min.js", ".min.css",
    }
    skip_names = {"package-lock.json", "yarn.lock", "uv.lock"}
    files = []
    for f in result.stdout.strip().splitlines():
        p = Path(f)
        if p.suffix.lower() in skip_extensions:
            continue
        if p.name in skip_names:
            continue
        files.append(f)
    return files


def blame_file(repo_root: Path, filepath: str) -> dict[str, int]:
    """Run git blame on a file and return {author: line_count}."""
    try:
        result = subprocess.run(
            ["git", "blame", "--line-porcelain", filepath],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return {}

    counts: dict[str, int] = defaultdict(int)
    for line in result.stdout.splitlines():
        if line.startswith("author "):
            author = line[7:]
            counts[author] += 1
    return dict(counts)


def compute_bus_factor(ownership: dict[str, int]) -> int:
    """Number of top authors needed to cover >50% of total lines."""
    total = sum(ownership.values())
    if total == 0:
        return 0
    sorted_authors = sorted(ownership.values(), reverse=True)
    cumulative = 0
    for i, count in enumerate(sorted_authors, 1):
        cumulative += count
        if cumulative > total / 2:
            return i
    return len(sorted_authors)


def analyze(repo_root: Path) -> dict:
    """Run full bus-factor analysis and return structured results."""
    files = get_tracked_files(repo_root)
    total_ownership: dict[str, int] = defaultdict(int)
    module_ownership: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    file_results = []

    for filepath in files:
        authors = blame_file(repo_root, filepath)
        if not authors:
            continue

        total_lines = sum(authors.values())
        top_author = max(authors, key=authors.get) if authors else None
        top_pct = (authors[top_author] / total_lines * 100) if top_author else 0

        file_results.append({
            "file": filepath,
            "lines": total_lines,
            "authors": len(authors),
            "top_author": top_author,
            "top_author_pct": round(top_pct, 1),
        })

        # Aggregate into totals and modules
        module = filepath.split("/")[0] if "/" in filepath else "(root)"
        for author, count in authors.items():
            total_ownership[author] += count
            module_ownership[module][author] += count

    total_lines = sum(total_ownership.values())
    bus_factor = compute_bus_factor(dict(total_ownership))

    # Build author summary sorted by lines desc
    author_summary = []
    for author, lines in sorted(total_ownership.items(), key=lambda x: -x[1]):
        author_summary.append({
            "author": author,
            "lines": lines,
            "pct": round(lines / total_lines * 100, 1) if total_lines else 0,
        })

    # Build module summary
    module_summary = []
    for module in sorted(module_ownership):
        mod_authors = module_ownership[module]
        mod_total = sum(mod_authors.values())
        mod_bf = compute_bus_factor(dict(mod_authors))
        top = max(mod_authors, key=mod_authors.get)
        module_summary.append({
            "module": module,
            "lines": mod_total,
            "authors": len(mod_authors),
            "bus_factor": mod_bf,
            "top_author": top,
            "top_author_pct": round(mod_authors[top] / mod_total * 100, 1),
        })

    return {
        "repo": str(repo_root),
        "total_lines": total_lines,
        "total_files": len(file_results),
        "bus_factor": bus_factor,
        "authors": author_summary,
        "modules": module_summary,
        "files": sorted(file_results, key=lambda x: -x["lines"]),
    }


def render_markdown(data: dict) -> str:
    """Render analysis results as markdown."""
    lines = [
        "# Bus-Factor Report",
        "",
        f"**Repository:** `{data['repo']}`  ",
        f"**Total lines:** {data['total_lines']:,}  ",
        f"**Total files:** {data['total_files']}  ",
        f"**Bus factor:** {data['bus_factor']}  ",
        "",
        "## Author Ownership",
        "",
        "| Author | Lines | % |",
        "|--------|------:|--:|",
    ]
    for a in data["authors"]:
        lines.append(f"| {a['author']} | {a['lines']:,} | {a['pct']}% |")

    lines += [
        "",
        "## Module Breakdown",
        "",
        "| Module | Lines | Authors | Bus Factor | Top Author | Top % |",
        "|--------|------:|--------:|-----------:|------------|------:|",
    ]
    for m in data["modules"]:
        lines.append(
            f"| {m['module']} | {m['lines']:,} | {m['authors']} "
            f"| {m['bus_factor']} | {m['top_author']} | {m['top_author_pct']}% |"
        )

    lines += [
        "",
        "## Top Files by Size",
        "",
        "| File | Lines | Authors | Top Author | Top % |",
        "|------|------:|--------:|------------|------:|",
    ]
    for f in data["files"][:20]:
        lines.append(
            f"| {f['file']} | {f['lines']:,} | {f['authors']} "
            f"| {f['top_author']} | {f['top_author_pct']}% |"
        )
    if len(data["files"]) > 20:
        lines.append(f"| *... {len(data['files']) - 20} more files* | | | | |")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze git repository bus factor")
    parser.add_argument(
        "--repo-root", type=Path, default=Path("."),
        help="Root of the git repository (default: current directory)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--format", choices=["json", "markdown"], default="markdown",
        dest="fmt",
        help="Output format (default: markdown)",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    data = analyze(repo_root)

    if args.fmt == "json":
        output = json.dumps(data, indent=2)
    else:
        output = render_markdown(data)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
