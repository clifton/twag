#!/usr/bin/env python3
"""Analyze git history and codebase structure to identify knowledge silos.

Produces a Markdown report highlighting bus-factor risks, untested modules,
and complexity hotspots that concentrate institutional knowledge.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ModuleInfo:
    path: str
    lines: int = 0
    functions: int = 0
    classes: int = 0
    commits: int = 0
    authors: set[str] = field(default_factory=set)
    has_tests: bool = False
    test_file: str | None = None
    test_lines: int = 0


def run(cmd: str) -> str:
    return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()


def find_modules(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in str(p) and p.name != "__init__.py")


def count_constructs(path: Path) -> tuple[int, int, int]:
    lines = funcs = classes = 0
    try:
        for line in path.read_text().splitlines():
            lines += 1
            stripped = line.lstrip()
            if stripped.startswith(("def ", "async def ")):
                funcs += 1
            elif stripped.startswith("class "):
                classes += 1
    except Exception:
        pass
    return lines, funcs, classes


def git_stats(path: str) -> tuple[int, set[str]]:
    try:
        log = run(f"git log --all --format='%an' -- '{path}'")
        authors = {a for a in log.splitlines() if a}
        return len(log.splitlines()), authors
    except Exception:
        return 0, set()


def find_test(module_path: Path, test_dir: Path) -> Path | None:
    stem = module_path.stem
    for candidate in test_dir.rglob(f"test_{stem}*.py"):
        return candidate
    for candidate in test_dir.rglob(f"test_*{stem}*.py"):
        return candidate
    return None


def analyze(repo_root: Path) -> list[ModuleInfo]:
    src_root = repo_root / "twag"
    test_dir = repo_root / "tests"
    modules = find_modules(src_root)

    results = []
    for mod_path in modules:
        rel = str(mod_path.relative_to(repo_root))
        lines, funcs, classes = count_constructs(mod_path)
        commits, authors = git_stats(rel)

        test_path = find_test(mod_path, test_dir)
        has_tests = test_path is not None
        test_lines = 0
        if test_path:
            test_lines = len(test_path.read_text().splitlines())

        results.append(
            ModuleInfo(
                path=rel,
                lines=lines,
                functions=funcs,
                classes=classes,
                commits=commits,
                authors=authors,
                has_tests=has_tests,
                test_file=str(test_path.relative_to(repo_root)) if test_path else None,
                test_lines=test_lines,
            ),
        )

    return results


def bus_factor(authors: set[str]) -> int:
    return len(authors)


def risk_score(m: ModuleInfo) -> float:
    score = 0.0
    # Large files are riskier
    if m.lines > 500:
        score += 3
    elif m.lines > 300:
        score += 2
    elif m.lines > 150:
        score += 1

    # No tests = higher risk
    if not m.has_tests:
        score += 3

    # Low test-to-code ratio
    if m.has_tests and m.lines > 0:
        ratio = m.test_lines / m.lines
        if ratio < 0.3:
            score += 1

    # Single author = bus factor risk
    if bus_factor(m.authors) <= 1:
        score += 2

    # High complexity (many functions)
    if m.functions > 15:
        score += 2
    elif m.functions > 10:
        score += 1

    # High churn
    if m.commits > 30:
        score += 1

    return score


def generate_report(modules: list[ModuleInfo]) -> str:
    lines: list[str] = []
    lines.append("# Knowledge Silo Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")

    all_authors = set()
    for m in modules:
        all_authors |= m.authors
    total_modules = len(modules)
    untested = [m for m in modules if not m.has_tests]
    total_lines = sum(m.lines for m in modules)

    lines.append(f"- **Contributors:** {len(all_authors)} ({', '.join(sorted(all_authors))})")
    lines.append(f"- **Project bus factor:** {len(all_authors)}")
    lines.append(f"- **Total modules:** {total_modules}")
    lines.append(f"- **Total source lines:** {total_lines:,}")
    lines.append(
        f"- **Modules without tests:** {len(untested)} / {total_modules} ({100 * len(untested) // total_modules}%)",
    )
    lines.append("")

    if len(all_authors) == 1:
        lines.append("> **Critical:** This project has a bus factor of 1. All institutional")
        lines.append("> knowledge is concentrated in a single contributor. Every module is a")
        lines.append("> knowledge silo by definition.")
        lines.append("")

    # Top risk modules
    scored = sorted(modules, key=risk_score, reverse=True)
    lines.append("## Highest-Risk Knowledge Silos")
    lines.append("")
    lines.append("Modules ranked by composite risk (size + complexity + test coverage + bus factor):")
    lines.append("")
    lines.append("| Risk | Module | Lines | Funcs | Tests | Bus Factor | Commits |")
    lines.append("|------|--------|------:|------:|-------|-----------|--------:|")

    for m in scored[:20]:
        rs = risk_score(m)
        risk_label = "🔴" if rs >= 7 else "🟠" if rs >= 5 else "🟡" if rs >= 3 else "🟢"
        test_label = f"Yes ({m.test_lines}L)" if m.has_tests else "**None**"
        bf = bus_factor(m.authors)
        lines.append(
            f"| {risk_label} {rs:.0f} | `{m.path}` | {m.lines} | {m.functions} | {test_label} | {bf} | {m.commits} |",
        )

    lines.append("")

    # Untested modules detail
    lines.append("## Untested Modules (Highest Silo Risk)")
    lines.append("")
    lines.append("These modules have zero test coverage, making them the hardest to")
    lines.append("understand and safely modify without the original author:")
    lines.append("")

    untested_sorted = sorted(untested, key=lambda m: m.lines, reverse=True)
    lines.extend(f"- **`{m.path}`** — {m.lines} lines, {m.functions} functions" for m in untested_sorted)

    lines.append("")

    # Complexity hotspots
    lines.append("## Complexity Hotspots")
    lines.append("")
    lines.append("Modules with >10 functions or >400 lines concentrate the most logic:")
    lines.append("")

    hotspots = [m for m in modules if m.functions > 10 or m.lines > 400]
    hotspots.sort(key=lambda m: m.lines, reverse=True)
    for m in hotspots:
        test_note = f"tested ({m.test_lines}L)" if m.has_tests else "**untested**"
        lines.append(f"- `{m.path}` — {m.lines} lines, {m.functions} functions, {test_note}")

    lines.append("")

    # Subsystem breakdown
    lines.append("## Subsystem Risk Summary")
    lines.append("")

    subsystems: dict[str, list[ModuleInfo]] = defaultdict(list)
    for m in modules:
        parts = m.path.split("/")
        if len(parts) >= 3:
            subsystem = "/".join(parts[:3])
        else:
            subsystem = parts[0] + "/" + parts[1] if len(parts) >= 2 else parts[0]
        subsystems[subsystem].append(m)

    lines.append("| Subsystem | Modules | Lines | Untested | Avg Risk |")
    lines.append("|-----------|--------:|------:|---------:|---------:|")

    for sub in sorted(subsystems.keys()):
        mods = subsystems[sub]
        sub_lines = sum(m.lines for m in mods)
        sub_untested = sum(1 for m in mods if not m.has_tests)
        avg_risk = sum(risk_score(m) for m in mods) / len(mods) if mods else 0
        lines.append(f"| `{sub}` | {len(mods)} | {sub_lines} | {sub_untested} | {avg_risk:.1f} |")

    lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    lines.append("### Immediate (reduce silo risk)")
    lines.append("1. **Add tests for the top untested modules** — especially `processor/triage.py` (862L),")
    lines.append("   `processor/dependencies.py` (538L), and `web/routes/context.py` (483L)")
    lines.append("2. **Add inline docstrings** to complex functions in high-risk modules")
    lines.append("3. **Break up large modules** — `processor/triage.py` at 862 lines should be split")
    lines.append("")
    lines.append("### Strategic (increase bus factor)")
    lines.append("4. **Document architectural decisions** in ADRs or a DECISIONS.md")
    lines.append("5. **Write subsystem guides** for processor pipeline, scorer, and web routes")
    lines.append("6. **Pair-program or code-review** critical path modules with a second contributor")
    lines.append("")

    return "\n".join(lines)


def main():
    repo_root = Path(__file__).resolve().parent.parent
    if not (repo_root / "twag").is_dir():
        print("Error: run from the twag repository root", file=sys.stderr)
        sys.exit(1)

    os.chdir(repo_root)
    modules = analyze(repo_root)
    report = generate_report(modules)

    output_path = repo_root / "tmp" / "knowledge_silo_report.md"
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(report)
    print(f"Report written to {output_path}")

    # Also print to stdout
    print()
    print(report)


if __name__ == "__main__":
    main()
