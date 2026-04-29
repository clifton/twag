#!/usr/bin/env python3
"""Test flakiness analyzer for the twag pytest suite.

Combines two complementary signals:

1. Dynamic detection — runs pytest N times (optionally with pytest-randomly
   to shuffle test order) and diffs per-test outcomes across runs. Tests that
   sometimes pass and sometimes fail are flagged as flaky.

2. Static detection — grep-style smell scan of tests/ for common flakiness
   patterns: unmocked sleeps, real clocks, unseeded randomness, network I/O,
   filesystem writes outside tmp_path, and dict/set ordering assumptions.

Output is a markdown baseline report (default: docs/test_flakiness_report.md).

Examples:

    # Full analysis with 5 runs, randomized order
    uv run python scripts/analyze_test_flakiness.py

    # Static-only (no test runs — fast)
    uv run python scripts/analyze_test_flakiness.py --static-only

    # Dynamic with custom run count
    uv run python scripts/analyze_test_flakiness.py --runs 10 --no-randomize
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TESTS_DIR = REPO_ROOT / "tests"
DEFAULT_REPORT_PATH = REPO_ROOT / "docs" / "test_flakiness_report.md"


# ---------------------------------------------------------------------------
# Dynamic detection
# ---------------------------------------------------------------------------


@dataclass
class TestOutcome:
    """Outcome of a single test in a single run."""

    nodeid: str
    status: str  # "passed", "failed", "error", "skipped"
    duration: float = 0.0
    message: str = ""


@dataclass
class RunResult:
    """Result of one pytest invocation."""

    run_index: int
    seed: int | None
    outcomes: list[TestOutcome]
    returncode: int


@dataclass
class FlakyTest:
    """A test whose outcome was not consistent across runs."""

    nodeid: str
    statuses: list[str]
    pass_count: int
    fail_count: int
    last_message: str = ""


def parse_junit_xml(xml_text: str) -> list[TestOutcome]:
    """Parse a pytest --junit-xml report into TestOutcomes.

    Pure function — returns one TestOutcome per <testcase> element.
    Status precedence: error > failed > skipped > passed.
    """
    outcomes: list[TestOutcome] = []
    if not xml_text.strip():
        return outcomes

    root = ET.fromstring(xml_text)
    # JUnit XML may have <testsuites> wrapping or just <testsuite> at root.
    suites: Iterable[ET.Element]
    if root.tag == "testsuites":
        suites = list(root.findall("testsuite"))
    else:
        suites = [root]

    for suite in suites:
        for case in suite.findall("testcase"):
            classname = case.attrib.get("classname", "")
            name = case.attrib.get("name", "")
            duration = float(case.attrib.get("time", "0") or 0.0)

            # Build a pytest-style nodeid: "path::test_name". classname is
            # already the dotted import path; rebuild a path-like form.
            nodeid = _classname_to_nodeid(classname, name)

            error_el = case.find("error")
            failure_el = case.find("failure")
            skipped_el = case.find("skipped")

            status = "passed"
            message = ""
            if error_el is not None:
                status = "error"
                message = (error_el.attrib.get("message", "") or error_el.text or "").strip()
            elif failure_el is not None:
                status = "failed"
                message = (failure_el.attrib.get("message", "") or failure_el.text or "").strip()
            elif skipped_el is not None:
                status = "skipped"
                message = (skipped_el.attrib.get("message", "") or skipped_el.text or "").strip()

            outcomes.append(
                TestOutcome(
                    nodeid=nodeid,
                    status=status,
                    duration=duration,
                    message=message[:500],
                ),
            )

    return outcomes


def _classname_to_nodeid(classname: str, name: str) -> str:
    """Convert a JUnit classname + testname into a pytest nodeid-ish string.

    JUnit classname is usually ``tests.test_foo`` or ``tests.test_foo.TestClass``.
    Pytest nodeids look like ``tests/test_foo.py::test_name`` or
    ``tests/test_foo.py::TestClass::test_name``. We do a best-effort rebuild.
    """
    if not classname:
        return name
    parts = classname.split(".")
    # Find the file part — the last segment that starts with "test_".
    file_idx = -1
    for i, part in enumerate(parts):
        if part.startswith("test_") or part == "conftest":
            file_idx = i
    if file_idx == -1:
        return f"{classname}::{name}"
    file_path = "/".join(parts[: file_idx + 1]) + ".py"
    rest = parts[file_idx + 1 :]
    if rest:
        return f"{file_path}::{'::'.join(rest)}::{name}"
    return f"{file_path}::{name}"


def run_pytest_once(
    run_index: int,
    randomize: bool,
    seed: int | None,
    extra_args: list[str],
    cwd: Path,
) -> RunResult:
    """Invoke pytest once with --junit-xml and return parsed outcomes."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=f"_run{run_index}.xml", delete=False) as tmp:
        xml_path = Path(tmp.name)

    cmd: list[str] = [
        "uv",
        "run",
        "pytest",
        f"--junit-xml={xml_path}",
        "-p",
        "no:cacheprovider",
        "--tb=short",
    ]
    if randomize:
        # pytest-randomly uses --randomly-seed; if plugin is absent, pytest
        # ignores unknown options as long as they're routed via -p. Since the
        # flag is plugin-specific, we pass it conditionally.
        if seed is not None:
            cmd.append(f"--randomly-seed={seed}")
    else:
        cmd += ["-p", "no:randomly"]

    cmd += extra_args

    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )

    try:
        xml_text = xml_path.read_text() if xml_path.exists() else ""
    finally:
        xml_path.unlink(missing_ok=True)

    outcomes = parse_junit_xml(xml_text) if xml_text else []
    return RunResult(
        run_index=run_index,
        seed=seed,
        outcomes=outcomes,
        returncode=proc.returncode,
    )


def aggregate_outcomes(runs: list[RunResult]) -> dict[str, list[str]]:
    """Aggregate per-test status lists across runs.

    Returns a mapping of nodeid -> list of statuses, in run order.
    Tests missing from a run are recorded as 'missing' (e.g. selection
    differences across randomized orders are rare but possible).
    """
    all_nodeids: set[str] = set()
    per_run: list[dict[str, str]] = []
    for run in runs:
        run_map = {o.nodeid: o.status for o in run.outcomes}
        per_run.append(run_map)
        all_nodeids.update(run_map.keys())

    aggregated: dict[str, list[str]] = {}
    for nodeid in sorted(all_nodeids):
        aggregated[nodeid] = [run_map.get(nodeid, "missing") for run_map in per_run]
    return aggregated


def classify_flaky(aggregated: dict[str, list[str]]) -> list[FlakyTest]:
    """Identify tests with mixed pass/fail outcomes across runs.

    A test is flaky iff it has both a pass and a non-pass (failed/error)
    outcome. Tests that always fail or always pass are not flaky.
    Skipped/missing statuses are ignored for the flaky/stable decision.
    """
    flaky: list[FlakyTest] = []
    for nodeid, statuses in aggregated.items():
        passes = sum(1 for s in statuses if s == "passed")
        fails = sum(1 for s in statuses if s in {"failed", "error"})
        if passes > 0 and fails > 0:
            flaky.append(
                FlakyTest(
                    nodeid=nodeid,
                    statuses=statuses,
                    pass_count=passes,
                    fail_count=fails,
                ),
            )
    flaky.sort(key=lambda f: (-f.fail_count, f.nodeid))
    return flaky


# ---------------------------------------------------------------------------
# Static detection
# ---------------------------------------------------------------------------


@dataclass
class StaticSmell:
    """A static-analysis flakiness smell occurrence."""

    file: str
    line: int
    category: str
    snippet: str


# Smell category -> compiled regex. Each regex matches per-line.
SMELL_PATTERNS: dict[str, re.Pattern[str]] = {
    "real_sleep": re.compile(r"\b(?:time\.)?sleep\s*\("),
    "real_clock_now": re.compile(r"\bdatetime\.(?:now|utcnow|today)\s*\("),
    "real_clock_time": re.compile(r"\btime\.(?:time|monotonic|perf_counter)\s*\("),
    "unseeded_random": re.compile(r"\brandom\.(?:random|randint|choice|sample|shuffle|uniform|gauss)\s*\("),
    "real_network": re.compile(r"\b(?:requests|httpx)\.(?:get|post|put|delete|request)\s*\(|urlopen\s*\("),
    "abs_filesystem_write": re.compile(r"""open\s*\(\s*['"]/(?!tmp/)|Path\s*\(\s*['"]/(?!tmp/)"""),
    "ordering_assumption": re.compile(r"==\s*list\s*\(\s*(?:\{|set\(|dict\()"),
}

# Lines containing any of these tokens are exempt from the indicated category.
SMELL_EXEMPTIONS: dict[str, re.Pattern[str]] = {
    "real_sleep": re.compile(r"\b(?:freezegun|asyncio\.sleep|monkeypatch|mock|Mock)\b"),
    "real_clock_now": re.compile(r"\b(?:freeze_time|freezegun|monkeypatch|mock|Mock)\b"),
    "real_clock_time": re.compile(r"\b(?:freeze_time|freezegun|monkeypatch|mock|Mock)\b"),
    "unseeded_random": re.compile(r"\brandom\.seed\b"),
    "real_network": re.compile(r"\b(?:respx|httpx_mock|monkeypatch|mock|Mock|patch)\b"),
}


def scan_file_for_smells(file_path: Path, content: str) -> list[StaticSmell]:
    """Scan a single file's text for flakiness smells. Pure function."""
    smells: list[StaticSmell] = []
    has_seed = bool(re.search(r"\brandom\.seed\s*\(", content))
    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for category, pattern in SMELL_PATTERNS.items():
            if not pattern.search(line):
                continue
            # Per-line exemption check.
            exempt = SMELL_EXEMPTIONS.get(category)
            if exempt and exempt.search(line):
                continue
            # File-level exemption: unseeded_random is forgiven if the file
            # calls random.seed() somewhere.
            if category == "unseeded_random" and has_seed:
                continue
            snippet = stripped[:160]
            smells.append(
                StaticSmell(
                    file=str(file_path),
                    line=lineno,
                    category=category,
                    snippet=snippet,
                ),
            )
    return smells


DEFAULT_SCAN_EXCLUDES: frozenset[str] = frozenset(
    {
        "__init__.py",
        # The analyzer's own test file contains deliberate fixture strings that
        # match every smell pattern. Skip it to avoid self-referential noise.
        "test_flakiness_analyzer.py",
    },
)


def scan_tests_dir(tests_dir: Path, excludes: frozenset[str] = DEFAULT_SCAN_EXCLUDES) -> list[StaticSmell]:
    """Walk the tests directory and collect static smells."""
    all_smells: list[StaticSmell] = []
    for path in sorted(tests_dir.rglob("*.py")):
        if path.name in excludes:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(tests_dir.parent)
        all_smells.extend(scan_file_for_smells(rel, content))
    return all_smells


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


@dataclass
class AnalyzerReport:
    runs: list[RunResult] = field(default_factory=list)
    aggregated: dict[str, list[str]] = field(default_factory=dict)
    flaky: list[FlakyTest] = field(default_factory=list)
    smells: list[StaticSmell] = field(default_factory=list)
    randomize: bool = True
    static_only: bool = False


def render_markdown(report: AnalyzerReport) -> str:
    """Render the analyzer report as markdown."""
    lines: list[str] = []
    lines.append("# Test Flakiness Baseline Report")
    lines.append("")
    lines.append(
        "Generated by `scripts/analyze_test_flakiness.py`. Combines dynamic "
        "(N pytest runs) and static (smell scan) signals.",
    )
    lines.append("")

    # Dynamic section ------------------------------------------------------
    lines.append("## Dynamic detection")
    lines.append("")
    if report.static_only:
        lines.append("_Skipped (--static-only)._")
        lines.append("")
    elif not report.runs:
        lines.append("_No runs completed._")
        lines.append("")
    else:
        total_tests = len(report.aggregated)
        flaky_count = len(report.flaky)
        always_fail = sum(
            1 for statuses in report.aggregated.values() if all(s in {"failed", "error"} for s in statuses)
        )
        lines.append(f"- **Runs:** {len(report.runs)}")
        lines.append(f"- **Order randomization:** {'on' if report.randomize else 'off'}")
        lines.append(f"- **Distinct tests observed:** {total_tests}")
        lines.append(f"- **Flaky (mixed outcomes):** {flaky_count}")
        lines.append(f"- **Consistently failing:** {always_fail}")
        lines.append("")

        # Per-run summary line.
        lines.append("### Per-run summary")
        lines.append("")
        lines.append("| Run | Seed | Return code | Outcomes parsed |")
        lines.append("| --- | --- | --- | --- |")
        for run in report.runs:
            seed_repr = "-" if run.seed is None else str(run.seed)
            lines.append(f"| {run.run_index} | {seed_repr} | {run.returncode} | {len(run.outcomes)} |")
        lines.append("")

        # Flaky list.
        lines.append("### Flaky tests")
        lines.append("")
        if not report.flaky:
            lines.append("_None detected._ All tests had consistent outcomes across runs.")
        else:
            lines.append("| nodeid | pass | fail | per-run statuses |")
            lines.append("| --- | --- | --- | --- |")
            for f in report.flaky:
                statuses_str = " · ".join(_short_status(s) for s in f.statuses)
                lines.append(f"| `{f.nodeid}` | {f.pass_count} | {f.fail_count} | {statuses_str} |")
            lines.append("")
            lines.append("#### Last failure messages")
            lines.append("")
            for f in report.flaky:
                if f.last_message:
                    lines.append(f"**`{f.nodeid}`**")
                    lines.append("")
                    lines.append("```")
                    lines.append(f.last_message)
                    lines.append("```")
                    lines.append("")
        lines.append("")

    # Static section -------------------------------------------------------
    lines.append("## Static smells")
    lines.append("")
    if not report.smells:
        lines.append("_None detected._")
    else:
        by_cat: dict[str, list[StaticSmell]] = defaultdict(list)
        for smell in report.smells:
            by_cat[smell.category].append(smell)
        lines.append("| category | count |")
        lines.append("| --- | --- |")
        lines.extend(f"| `{cat}` | {len(by_cat[cat])} |" for cat in sorted(by_cat))
        lines.append("")
        lines.append("### Occurrences")
        lines.append("")
        lines.append("| category | location | snippet |")
        lines.append("| --- | --- | --- |")
        for smell in report.smells:
            loc = f"{smell.file}:{smell.line}"
            snippet = smell.snippet.replace("|", "\\|")
            lines.append(f"| `{smell.category}` | `{loc}` | `{snippet}` |")
    lines.append("")

    # Action items ---------------------------------------------------------
    lines.append("## Action items")
    lines.append("")
    if not report.flaky and not report.smells:
        lines.append("_No items._ Suite is clean against this baseline scan.")
    else:
        if report.flaky:
            lines.append("**Flaky tests to triage:**")
            lines.append("")
            lines.extend(f"- [ ] `{f.nodeid}` — {f.pass_count}P / {f.fail_count}F" for f in report.flaky)
            lines.append("")
        if report.smells:
            lines.append(
                "**Static smells:** review the table above and either silence "
                "false positives, mock the resource, or restructure the test.",
            )
    lines.append("")

    return "\n".join(lines)


def _short_status(status: str) -> str:
    return {
        "passed": "P",
        "failed": "F",
        "error": "E",
        "skipped": "S",
        "missing": "-",
    }.get(status, status[:1].upper())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze the twag pytest suite for flakiness.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of pytest invocations for dynamic detection.",
    )
    parser.add_argument(
        "--no-randomize",
        action="store_true",
        help="Disable test-order randomization (pytest-randomly).",
    )
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Skip dynamic runs; only emit the static smell scan.",
    )
    parser.add_argument(
        "--tests-dir",
        type=Path,
        default=DEFAULT_TESTS_DIR,
        help="Tests directory to scan for static smells.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Output markdown report path.",
    )
    parser.add_argument(
        "--seeds",
        type=str,
        default="",
        help="Comma-separated list of seeds for runs (length must match --runs).",
    )
    parser.add_argument(
        "--pytest-args",
        type=str,
        default="",
        help="Extra args appended to each pytest invocation (split by spaces).",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to dump raw aggregated outcomes as JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    randomize = not args.no_randomize
    seeds: list[int | None]
    if args.seeds:
        try:
            seeds = [int(s) for s in args.seeds.split(",")]
        except ValueError:
            print("error: --seeds must be comma-separated integers", file=sys.stderr)
            return 2
        if len(seeds) != args.runs:
            print(
                f"error: --seeds count ({len(seeds)}) must equal --runs ({args.runs})",
                file=sys.stderr,
            )
            return 2
    else:
        seeds = [1000 + i for i in range(args.runs)] if randomize else [None] * args.runs

    extra_args = args.pytest_args.split() if args.pytest_args else []

    report = AnalyzerReport(randomize=randomize, static_only=args.static_only)

    # Static pass.
    print(f"[static] scanning {args.tests_dir}", file=sys.stderr)
    report.smells = scan_tests_dir(args.tests_dir)
    print(f"[static] {len(report.smells)} smell(s) found", file=sys.stderr)

    # Dynamic pass.
    if not args.static_only:
        for i in range(args.runs):
            seed = seeds[i]
            print(f"[dynamic] run {i + 1}/{args.runs} (seed={seed})", file=sys.stderr)
            run = run_pytest_once(
                run_index=i + 1,
                randomize=randomize,
                seed=seed,
                extra_args=extra_args,
                cwd=REPO_ROOT,
            )
            print(
                f"[dynamic] run {i + 1} rc={run.returncode} parsed={len(run.outcomes)}",
                file=sys.stderr,
            )
            report.runs.append(run)

        report.aggregated = aggregate_outcomes(report.runs)
        report.flaky = classify_flaky(report.aggregated)

        # Attach last failure message per flaky test.
        for f in report.flaky:
            for run in reversed(report.runs):
                hit = next(
                    (o for o in run.outcomes if o.nodeid == f.nodeid and o.status in {"failed", "error"}),
                    None,
                )
                if hit and hit.message:
                    f.last_message = hit.message
                    break

    # Emit markdown report.
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_markdown(report), encoding="utf-8")
    print(f"[report] wrote {args.report}", file=sys.stderr)

    if args.json_out is not None:
        payload = {
            "runs": [
                {
                    "run_index": r.run_index,
                    "seed": r.seed,
                    "returncode": r.returncode,
                    "outcomes": [
                        {
                            "nodeid": o.nodeid,
                            "status": o.status,
                            "duration": o.duration,
                            "message": o.message,
                        }
                        for o in r.outcomes
                    ],
                }
                for r in report.runs
            ],
            "aggregated": report.aggregated,
            "flaky": [
                {
                    "nodeid": f.nodeid,
                    "statuses": f.statuses,
                    "pass_count": f.pass_count,
                    "fail_count": f.fail_count,
                }
                for f in report.flaky
            ],
            "smells": [
                {
                    "file": s.file,
                    "line": s.line,
                    "category": s.category,
                    "snippet": s.snippet,
                }
                for s in report.smells
            ],
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[report] wrote {args.json_out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
