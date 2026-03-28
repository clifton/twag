"""Roadmap entropy detector — analyze git commit history for scope creep and drift.

Maps file changes to project areas, computes Shannon entropy of work distribution,
compares against optional roadmap focus-area weights, and flags drift signals.
"""

from __future__ import annotations

import math
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Area mapping
# ---------------------------------------------------------------------------

#: Ordered prefixes → area name.  First match wins.
AREA_PREFIXES: list[tuple[str, str]] = [
    ("twag/web/frontend/", "frontend"),
    ("twag/web/", "web"),
    ("twag/fetcher/", "fetcher"),
    ("twag/processor/", "processor"),
    ("twag/scorer/", "scorer"),
    ("twag/cli/", "cli"),
    ("twag/db/", "db"),
    ("scripts/", "scripts"),
    ("tests/", "tests"),
    ("twag/", "core"),  # remaining twag modules
]

DOC_EXTENSIONS = {".md", ".txt", ".rst"}
CONFIG_FILES = {
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    ".roadmap.yml",
    "ruff.toml",
    ".flake8",
    ".pre-commit-config.yaml",
    "Makefile",
}


def file_to_area(path: str) -> str:
    """Map a file path to a project area."""
    p = Path(path)

    # Docs
    if p.suffix in DOC_EXTENSIONS:
        return "docs"

    # Config files at repo root
    if p.name in CONFIG_FILES or path.startswith("."):
        return "config"

    for prefix, area in AREA_PREFIXES:
        if path.startswith(prefix):
            return area

    return "other"


# ---------------------------------------------------------------------------
# Git log parsing
# ---------------------------------------------------------------------------


@dataclass
class CommitInfo:
    sha: str
    subject: str
    files: list[str] = field(default_factory=list)
    areas: set[str] = field(default_factory=set)


def parse_git_log(days: int = 30, repo_path: str | None = None) -> list[CommitInfo]:
    """Parse ``git log --numstat`` for the given window and return commit info."""
    cmd = [
        "git",
        "log",
        f"--since={days} days ago",
        "--pretty=format:%H %s",
        "--numstat",
    ]
    kwargs: dict[str, Any] = {"capture_output": True, "text": True}
    if repo_path:
        kwargs["cwd"] = repo_path

    result = subprocess.run(cmd, check=False, **kwargs)
    if result.returncode != 0:
        raise RuntimeError(f"git log failed: {result.stderr.strip()}")

    commits: list[CommitInfo] = []
    current: CommitInfo | None = None

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # numstat lines start with digits (or '-' for binary)
        parts = line.split("\t")
        if len(parts) == 3 and (parts[0].isdigit() or parts[0] == "-"):
            filepath = parts[2]
            if current:
                current.files.append(filepath)
                current.areas.add(file_to_area(filepath))
        else:
            # commit header line: "<sha> <subject…>"
            sha, _, subject = line.partition(" ")
            current = CommitInfo(sha=sha, subject=subject)
            commits.append(current)

    return commits


# ---------------------------------------------------------------------------
# Entropy calculation
# ---------------------------------------------------------------------------


def shannon_entropy(counts: dict[str, int]) -> float:
    """Compute Shannon entropy (in bits) of a count distribution."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy


def max_entropy(n_categories: int) -> float:
    """Maximum possible entropy for *n_categories* (uniform distribution)."""
    if n_categories <= 1:
        return 0.0
    return math.log2(n_categories)


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


@dataclass
class DriftSignal:
    kind: str  # "new_area", "concentration_shift", "high_entropy_commit"
    description: str
    details: dict[str, Any] = field(default_factory=dict)


def detect_drift(
    commits: list[CommitInfo],
    roadmap_weights: dict[str, float] | None = None,
    high_entropy_threshold: float = 2.5,
) -> list[DriftSignal]:
    """Identify drift signals from commit history."""
    signals: list[DriftSignal] = []

    if not commits:
        return signals

    # Split history in halves to detect concentration shifts
    mid = len(commits) // 2
    first_half = commits[:mid] if mid > 0 else []
    second_half = commits[mid:]

    first_areas: Counter[str] = Counter()
    second_areas: Counter[str] = Counter()
    all_areas: Counter[str] = Counter()

    for c in first_half:
        for a in c.areas:
            first_areas[a] += 1
    for c in second_half:
        for a in c.areas:
            second_areas[a] += 1
    for c in commits:
        for a in c.areas:
            all_areas[a] += 1

    # New areas appearing in second half
    new_areas = set(second_areas) - set(first_areas)
    if new_areas and first_half:
        signals.append(
            DriftSignal(
                kind="new_area",
                description=f"New areas appeared in recent history: {', '.join(sorted(new_areas))}",
                details={"areas": sorted(new_areas)},
            )
        )

    # Concentration shifts — areas whose share changed significantly
    first_total = sum(first_areas.values()) or 1
    second_total = sum(second_areas.values()) or 1
    for area in set(first_areas) | set(second_areas):
        old_share = first_areas.get(area, 0) / first_total
        new_share = second_areas.get(area, 0) / second_total
        delta = new_share - old_share
        if abs(delta) > 0.25:
            direction = "increased" if delta > 0 else "decreased"
            signals.append(
                DriftSignal(
                    kind="concentration_shift",
                    description=f"Area '{area}' {direction} from {old_share:.0%} to {new_share:.0%}",
                    details={"area": area, "old_share": old_share, "new_share": new_share},
                )
            )

    # High-entropy commits (touching many unrelated areas)
    for c in commits:
        if len(c.areas) >= 3:
            area_counts = Counter(file_to_area(f) for f in c.files)
            e = shannon_entropy(dict(area_counts))
            if e >= high_entropy_threshold:
                signals.append(
                    DriftSignal(
                        kind="high_entropy_commit",
                        description=f"Commit {c.sha[:8]} touches {len(c.areas)} areas (entropy={e:.2f}): {c.subject}",
                        details={"sha": c.sha, "areas": sorted(c.areas), "entropy": e},
                    )
                )

    # Roadmap divergence
    if roadmap_weights:
        total_all = sum(all_areas.values()) or 1
        for area, expected_weight in roadmap_weights.items():
            actual_share = all_areas.get(area, 0) / total_all
            if expected_weight > 0 and actual_share < expected_weight * 0.5:
                signals.append(
                    DriftSignal(
                        kind="roadmap_underweight",
                        description=f"Area '{area}' has {actual_share:.0%} of work but roadmap expects ~{expected_weight:.0%}",
                        details={"area": area, "actual": actual_share, "expected": expected_weight},
                    )
                )
            if expected_weight == 0 and actual_share > 0.1:
                signals.append(
                    DriftSignal(
                        kind="roadmap_overweight",
                        description=f"Area '{area}' has {actual_share:.0%} of work but is not on the roadmap",
                        details={"area": area, "actual": actual_share},
                    )
                )

    return signals


# ---------------------------------------------------------------------------
# Roadmap config
# ---------------------------------------------------------------------------


def load_roadmap(path: str | Path) -> dict[str, float] | None:
    """Load roadmap focus-area weights from a YAML file. Returns *None* if missing."""
    p = Path(path)
    if not p.exists():
        return None
    with open(p) as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        return None
    areas = data.get("focus_areas")
    if not isinstance(areas, dict):
        return None
    return {str(k): float(v) for k, v in areas.items()}


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def build_report(
    commits: list[CommitInfo],
    signals: list[DriftSignal],
    roadmap_weights: dict[str, float] | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """Build a structured report dict."""
    area_counts: Counter[str] = Counter()
    area_files: dict[str, int] = defaultdict(int)

    for c in commits:
        for f in c.files:
            a = file_to_area(f)
            area_files[a] += 1
        for a in c.areas:
            area_counts[a] += 1

    total_commits = len(commits)
    total_files = sum(area_files.values())
    entropy = shannon_entropy(dict(area_counts))
    max_ent = max_entropy(len(area_counts)) if area_counts else 0.0
    normalized = entropy / max_ent if max_ent > 0 else 0.0

    area_breakdown = {}
    for area in sorted(area_counts):
        area_breakdown[area] = {
            "commits": area_counts[area],
            "files_changed": area_files.get(area, 0),
            "share": area_counts[area] / total_commits if total_commits else 0.0,
        }

    return {
        "window_days": days,
        "total_commits": total_commits,
        "total_files_changed": total_files,
        "unique_areas": len(area_counts),
        "entropy": round(entropy, 4),
        "max_entropy": round(max_ent, 4),
        "normalized_entropy": round(normalized, 4),
        "area_breakdown": area_breakdown,
        "drift_signals": [{"kind": s.kind, "description": s.description, "details": s.details} for s in signals],
        "roadmap_weights": roadmap_weights,
    }


def format_text_report(report: dict[str, Any]) -> str:
    """Render a human-readable text report."""
    lines: list[str] = []
    lines.append(f"Roadmap Entropy Report ({report['window_days']} days)")
    lines.append("=" * 50)
    lines.append(f"Commits analyzed: {report['total_commits']}")
    lines.append(f"Files changed:    {report['total_files_changed']}")
    lines.append(f"Unique areas:     {report['unique_areas']}")
    lines.append(f"Entropy:          {report['entropy']:.4f} / {report['max_entropy']:.4f} bits")
    lines.append(f"Normalized:       {report['normalized_entropy']:.2%}")
    lines.append("")

    lines.append("Area Breakdown")
    lines.append("-" * 40)
    for area, info in report["area_breakdown"].items():
        lines.append(f"  {area:<15} {info['commits']:>3} commits  {info['share']:>6.1%}")
    lines.append("")

    if report["drift_signals"]:
        lines.append("Drift Signals")
        lines.append("-" * 40)
        lines.extend(f"  [{s['kind']}] {s['description']}" for s in report["drift_signals"])
    else:
        lines.append("No drift signals detected.")

    return "\n".join(lines)
