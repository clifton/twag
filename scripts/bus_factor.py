#!/usr/bin/env python3
"""Bus-factor analyzer: per-file and per-module ownership concentration metrics.

Computes from git history:
  - unique authors per file
  - commit count per file
  - churn (lines added + removed)
  - last-modified date
  - composite risk score

Outputs JSON report and human-readable summary.
"""

import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(
    subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True
    ).strip()
)

# File extensions to analyze
TRACKED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css",
    ".json", ".yaml", ".yml", ".toml", ".cfg", ".md", ".sh",
}

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".eggs",
    "dist", "build", ".tox", ".venv", "venv",
}


def get_tracked_files():
    """Return list of tracked files in the repo."""
    out = subprocess.check_output(
        ["git", "ls-files"], text=True, cwd=REPO_ROOT
    )
    files = []
    for f in out.strip().splitlines():
        path = Path(f)
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.suffix in TRACKED_EXTENSIONS:
            files.append(f)
    return files


def get_file_log(filepath):
    """Get commit history for a file: authors, dates, commit count."""
    try:
        out = subprocess.check_output(
            ["git", "log", "--follow", "--format=%aN|%aI", "--", filepath],
            text=True, cwd=REPO_ROOT, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return [], [], 0

    authors = []
    dates = []
    for line in out.strip().splitlines():
        if "|" not in line:
            continue
        author, date_str = line.split("|", 1)
        authors.append(author.strip())
        dates.append(date_str.strip())

    return authors, dates, len(authors)


def get_file_churn(filepath):
    """Get total lines added and removed for a file across history."""
    try:
        out = subprocess.check_output(
            ["git", "log", "--follow", "--numstat", "--format=", "--", filepath],
            text=True, cwd=REPO_ROOT, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return 0, 0

    added = 0
    removed = 0
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        # Binary files show '-' for stats
        if parts[0] == "-":
            continue
        try:
            added += int(parts[0])
            removed += int(parts[1])
        except ValueError:
            continue

    return added, removed


def get_file_line_count(filepath):
    """Get current line count of a file."""
    full = REPO_ROOT / filepath
    if not full.exists():
        return 0
    try:
        return len(full.read_text(errors="replace").splitlines())
    except OSError:
        return 0


def compute_risk_score(unique_authors, commit_count, churn, line_count):
    """Compute a composite risk score (0-100).

    Higher = more risk of knowledge concentration.

    Factors:
    - Fewer unique authors → higher risk
    - Higher churn relative to size → higher risk (volatile code)
    - Higher commit count with few authors → higher risk
    """
    # Author concentration: 1 author = max risk
    if unique_authors <= 1:
        author_score = 100
    elif unique_authors == 2:
        author_score = 70
    elif unique_authors <= 4:
        author_score = 40
    else:
        author_score = max(10, 100 - unique_authors * 10)

    # Churn intensity: ratio of total churn to current size
    if line_count > 0:
        churn_ratio = churn / line_count
        churn_score = min(100, churn_ratio * 10)
    else:
        churn_score = 0

    # Commit density: many commits = actively changing = higher onboarding cost
    commit_score = min(100, commit_count * 3)

    # Weighted composite
    score = (author_score * 0.50) + (churn_score * 0.30) + (commit_score * 0.20)
    return round(min(100, score), 1)


def aggregate_modules(file_metrics):
    """Aggregate file metrics into per-module (directory) summaries."""
    modules = defaultdict(lambda: {
        "files": 0,
        "authors": set(),
        "total_commits": 0,
        "total_churn": 0,
        "total_lines": 0,
        "risk_scores": [],
    })

    for fm in file_metrics:
        # Use first two path components as module, or just the first
        parts = Path(fm["file"]).parts
        if len(parts) >= 2:
            module = str(Path(parts[0]) / parts[1])
        else:
            module = parts[0] if parts else "(root)"

        m = modules[module]
        m["files"] += 1
        m["authors"].update(fm["authors"])
        m["total_commits"] += fm["commit_count"]
        m["total_churn"] += fm["churn"]
        m["total_lines"] += fm["line_count"]
        m["risk_scores"].append(fm["risk_score"])

    result = []
    for module, m in sorted(modules.items()):
        avg_risk = round(sum(m["risk_scores"]) / len(m["risk_scores"]), 1) if m["risk_scores"] else 0
        result.append({
            "module": module,
            "files": m["files"],
            "unique_authors": len(m["authors"]),
            "total_commits": m["total_commits"],
            "total_churn": m["total_churn"],
            "total_lines": m["total_lines"],
            "avg_risk_score": avg_risk,
        })

    return sorted(result, key=lambda x: x["avg_risk_score"], reverse=True)


def analyze():
    """Run full bus-factor analysis."""
    files = get_tracked_files()
    print(f"Analyzing {len(files)} tracked files...", file=sys.stderr)

    file_metrics = []
    for i, filepath in enumerate(files):
        if (i + 1) % 50 == 0:
            print(f"  processed {i + 1}/{len(files)}...", file=sys.stderr)

        authors, dates, commit_count = get_file_log(filepath)
        added, removed = get_file_churn(filepath)
        line_count = get_file_line_count(filepath)
        unique_authors = sorted(set(authors))
        churn = added + removed

        last_modified = dates[0] if dates else None

        risk = compute_risk_score(len(unique_authors), commit_count, churn, line_count)

        file_metrics.append({
            "file": filepath,
            "authors": unique_authors,
            "unique_author_count": len(unique_authors),
            "commit_count": commit_count,
            "lines_added": added,
            "lines_removed": removed,
            "churn": churn,
            "line_count": line_count,
            "last_modified": last_modified,
            "risk_score": risk,
        })

    # Sort by risk descending
    file_metrics.sort(key=lambda x: x["risk_score"], reverse=True)
    module_metrics = aggregate_modules(file_metrics)

    # Summary stats
    all_authors = set()
    for fm in file_metrics:
        all_authors.update(fm["authors"])

    total_files = len(file_metrics)
    high_risk = [f for f in file_metrics if f["risk_score"] >= 70]
    medium_risk = [f for f in file_metrics if 40 <= f["risk_score"] < 70]

    report = {
        "generated_at": datetime.now().isoformat(),
        "repo_root": str(REPO_ROOT),
        "summary": {
            "total_files_analyzed": total_files,
            "total_unique_authors": len(all_authors),
            "authors": sorted(all_authors),
            "high_risk_files": len(high_risk),
            "medium_risk_files": len(medium_risk),
            "low_risk_files": total_files - len(high_risk) - len(medium_risk),
        },
        "top_risk_files": file_metrics[:20],
        "module_summary": module_metrics,
        "all_files": file_metrics,
    }

    return report


def print_summary(report):
    """Print human-readable summary to stdout."""
    s = report["summary"]
    print("=" * 70)
    print("BUS FACTOR ANALYSIS REPORT")
    print("=" * 70)
    print(f"Generated: {report['generated_at']}")
    print(f"Repository: {report['repo_root']}")
    print(f"Files analyzed: {s['total_files_analyzed']}")
    print(f"Unique authors: {s['total_unique_authors']} ({', '.join(s['authors'])})")
    print()
    print(f"Risk breakdown:")
    print(f"  HIGH  (>=70): {s['high_risk_files']} files")
    print(f"  MEDIUM (40-69): {s['medium_risk_files']} files")
    print(f"  LOW   (<40):  {s['low_risk_files']} files")

    print()
    print("-" * 70)
    print("TOP 20 HIGHEST-RISK FILES")
    print("-" * 70)
    print(f"{'Risk':>5}  {'Commits':>7}  {'Churn':>7}  {'Authors':>7}  File")
    print(f"{'-----':>5}  {'-------':>7}  {'-------':>7}  {'-------':>7}  ----")
    for f in report["top_risk_files"]:
        print(
            f"{f['risk_score']:>5.1f}  "
            f"{f['commit_count']:>7}  "
            f"{f['churn']:>7}  "
            f"{f['unique_author_count']:>7}  "
            f"{f['file']}"
        )

    print()
    print("-" * 70)
    print("MODULE SUMMARY (by avg risk)")
    print("-" * 70)
    print(f"{'AvgRisk':>7}  {'Files':>5}  {'Commits':>7}  {'Churn':>7}  Module")
    print(f"{'-------':>7}  {'-----':>5}  {'-------':>7}  {'-------':>7}  ------")
    for m in report["module_summary"]:
        print(
            f"{m['avg_risk_score']:>7.1f}  "
            f"{m['files']:>5}  "
            f"{m['total_commits']:>7}  "
            f"{m['total_churn']:>7}  "
            f"{m['module']}"
        )

    print()
    print("=" * 70)
    print("Key insights for single/low-author repos:")
    print("  - All files show high author-concentration risk by definition")
    print("  - Focus on CHURN and COMMIT COUNT to find onboarding hotspots")
    print("  - High-churn files need the most documentation/tests")
    print("  - Consider pairing on high-risk modules first")
    print("=" * 70)


def main():
    report = analyze()

    # Save JSON report
    out_dir = REPO_ROOT / "tmp"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "bus_factor_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nJSON report saved to: {out_path}", file=sys.stderr)

    # Print human-readable summary
    print_summary(report)


if __name__ == "__main__":
    main()
