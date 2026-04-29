#!/usr/bin/env python3
"""Repository PII / secret exposure scanner.

Scans tracked source files for credential patterns, risky logging, and
embedded personal data (emails, phone numbers).  Findings are grouped by
severity and emitted either as text (default) or as a Markdown report
(``--format markdown``).

Run modes:

* ``python scripts/pii_scan.py``               — print findings, exit 1 on high-severity findings.
* ``python scripts/pii_scan.py --report PII_SCAN_REPORT.md`` — write a Markdown report.
* ``python scripts/pii_scan.py --check``       — quiet mode, exit 1 on any high-severity finding.

The scanner is intentionally conservative: it ignores obvious test
fixtures, this script itself, and cached / generated paths.  A small
in-line allowlist suppresses values like ``"fake-token"`` that appear in
unit tests.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

# Files / directories that are skipped entirely.
EXCLUDE_DIR_PARTS = frozenset(
    {
        ".git",
        "node_modules",
        "dist",
        "build",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".ty",
        "htmlcov",
        "tmp",
        ".clawdhub",
        ".nightshift-plan",
    },
)

# Binary / generated extensions that have no value to scan.
EXCLUDE_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".pdf",
        ".gz",
        ".zip",
        ".whl",
        ".lock",
        ".sql",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
    },
)

# Files that legitimately contain matching strings (allowlist).
PATH_ALLOWLIST = frozenset(
    {
        # The scanner itself contains pattern strings; do not scan it.
        "scripts/pii_scan.py",
        # The pytest guard explicitly imports the scanner.
        "tests/test_pii_scan.py",
        # The generated report file is data, not source.
        "PII_SCAN_REPORT.md",
    },
)

# Substrings that, if found on a matched line, downgrade or suppress the match.
SAFE_VALUE_TOKENS = (
    "fake-token",
    "fake_token",
    "test-token",
    "test_token",
    "<redacted",
    "your_",
    "YOUR_",
    "example.com",
    "EXAMPLE",
)

# Per-line suppression marker.  Append "# pii-scan: ignore" (and optionally
# a reason) to a line to silence findings on that line.
SUPPRESSION_MARKER = "pii-scan: ignore"


@dataclass(frozen=True)
class Rule:
    """A single regex-based detection rule."""

    name: str
    pattern: re.Pattern[str]
    severity: str
    description: str
    file_globs: tuple[str, ...] = ()  # if set, only scan files whose name matches
    skip_test_paths: bool = True


# --- Rules -----------------------------------------------------------------

# High-severity: literal credential values.
RULES: tuple[Rule, ...] = (
    Rule(
        name="google_api_key",
        pattern=re.compile(r"AIza[0-9A-Za-z_-]{35}"),
        severity=SEVERITY_HIGH,
        description="Google / Gemini API key literal (AIza...).",
    ),
    Rule(
        name="openai_api_key",
        pattern=re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{32,}"),
        severity=SEVERITY_HIGH,
        description="OpenAI-style API key literal (sk-...).",
    ),
    Rule(
        name="anthropic_api_key",
        pattern=re.compile(r"sk-ant-[A-Za-z0-9_-]{32,}"),
        severity=SEVERITY_HIGH,
        description="Anthropic API key literal (sk-ant-...).",
    ),
    Rule(
        name="github_token",
        pattern=re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
        severity=SEVERITY_HIGH,
        description="GitHub personal access / app token literal.",
    ),
    Rule(
        name="slack_token",
        pattern=re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
        severity=SEVERITY_HIGH,
        description="Slack token literal (xoxb-, xoxp-, ...).",
    ),
    Rule(
        name="aws_access_key",
        pattern=re.compile(r"AKIA[0-9A-Z]{16}"),
        severity=SEVERITY_HIGH,
        description="AWS access key id literal (AKIA...).",
    ),
    Rule(
        name="telegram_bot_token",
        pattern=re.compile(r"\b\d{8,11}:[A-Za-z0-9_-]{30,}\b"),
        severity=SEVERITY_HIGH,
        description="Telegram bot token literal (digits:alnum).",
    ),
    Rule(
        name="twitter_auth_token_assignment",
        pattern=re.compile(
            r"""(?xi)
            \b(?:auth_token|ct0)\b
            \s*[:=]\s*
            ['"]?(?P<value>[0-9a-f]{30,})['"]?
            """,
        ),
        severity=SEVERITY_HIGH,
        description="Twitter session cookie literal assigned to auth_token / ct0.",
    ),
    Rule(
        name="generic_secret_assignment",
        pattern=re.compile(
            r"""(?xi)
            \b(?:password|passwd|secret|api[_-]?key|access[_-]?token|bearer)\b
            \s*[:=]\s*
            ['"](?P<value>[A-Za-z0-9_\-./+=]{16,})['"]
            """,
        ),
        severity=SEVERITY_HIGH,
        description="Generic secret-like assignment with quoted long literal.",
    ),
    # Medium-severity: risky logging / printing of sensitive identifiers.
    Rule(
        name="risky_log_of_secret",
        pattern=re.compile(
            r"""(?xi)
            \b(?:print|log|logger|logging)\s*[.(] [^()\n]*?
            \b(?:auth_token|ct0|password|api[_-]?key|secret|bearer|telegram_bot_token)\b
            """,
        ),
        severity=SEVERITY_MEDIUM,
        description="Logging / print statement that names a secret variable.",
        file_globs=("*.py",),
    ),
    Rule(
        name="risky_fstring_secret",
        pattern=re.compile(
            r"""(?xi)
            f['"][^'"]*\{(?:auth_token|ct0|password|api[_-]?key|secret|bearer|bot_token)\}[^'"]*['"]
            """,
        ),
        severity=SEVERITY_MEDIUM,
        description="f-string that interpolates a sensitive variable.",
        file_globs=("*.py",),
    ),
    # Low-severity: PII patterns (emails, US phone numbers).
    Rule(
        name="email_address",
        pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        severity=SEVERITY_LOW,
        description="Email address literal (likely a PII / sample address).",
    ),
    Rule(
        name="us_phone_number",
        pattern=re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?[2-9]\d{2}\)?[\s.-]?[2-9]\d{2}[\s.-]?\d{4}(?!\d)"),
        severity=SEVERITY_LOW,
        description="US-format phone number literal.",
    ),
)


@dataclass
class Finding:
    rule: Rule
    path: Path
    line_no: int
    line: str

    @property
    def relative_path(self) -> str:
        return _safe_relative(self.path)


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0

    def by_severity(self, severity: str) -> list[Finding]:
        return [f for f in self.findings if f.rule.severity == severity]


# --- File discovery --------------------------------------------------------


def _git_tracked_files(root: Path) -> list[Path]:
    """Return files tracked by git, falling back to a directory walk."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return _walk_files(root)
    paths = [root / name for name in result.stdout.decode().split("\0") if name]
    return [p for p in paths if p.is_file()]


def _walk_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            rel_parts = path.parts
        if any(part in EXCLUDE_DIR_PARTS for part in rel_parts):
            continue
        out.append(path)
    return out


def _is_test_path(rel: str) -> bool:
    """Return True for repo-relative paths that live under tests/ or scripts/.

    Operates on repo-relative strings; absolute paths are treated as non-test
    so that synthetic fixtures in /tmp/... are scanned during unit tests.
    """
    if rel.startswith("/"):
        return False
    parts = rel.split("/")
    return bool(parts) and parts[0] in {"tests", "scripts"}


def _safe_relative(path: Path) -> str:
    """Return a repo-relative path string, falling back to ``str(path)``."""
    if not path.is_absolute():
        return str(path)
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _allowed(path: Path) -> bool:
    rel = _safe_relative(path)
    if rel in PATH_ALLOWLIST:
        return False
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    # Only enforce dir-name exclusions on paths that are inside REPO_ROOT — this
    # keeps test callers passing synthetic temp paths (in /tmp/...) from being
    # filtered out by ambient directory names.
    if path.is_absolute():
        try:
            rel_parts = path.relative_to(REPO_ROOT).parts
        except ValueError:
            return True
    else:
        rel_parts = path.parts
    if any(part in EXCLUDE_DIR_PARTS for part in rel_parts):
        return False
    return True


# --- Scanning --------------------------------------------------------------


def _line_is_safe(line: str) -> bool:
    if SUPPRESSION_MARKER in line:
        return True
    return any(token in line for token in SAFE_VALUE_TOKENS)


def _rule_applies(rule: Rule, rel_path: str) -> bool:
    if rule.skip_test_paths and _is_test_path(rel_path):
        return False
    if rule.file_globs:
        path = Path(rel_path)
        return any(path.match(g) for g in rule.file_globs)
    return True


def scan_paths(paths: Iterable[Path]) -> ScanResult:
    result = ScanResult()
    for path in paths:
        if not _allowed(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        result.files_scanned += 1
        rel = _safe_relative(path)
        for rule in RULES:
            if not _rule_applies(rule, rel):
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if not rule.pattern.search(line):
                    continue
                if _line_is_safe(line):
                    continue
                result.findings.append(Finding(rule=rule, path=path, line_no=line_no, line=line.rstrip()))
    return result


def scan_repo(root: Path = REPO_ROOT) -> ScanResult:
    return scan_paths(_git_tracked_files(root))


def collect_suppressions(root: Path = REPO_ROOT) -> list[tuple[str, int, str]]:
    """Return ``(rel_path, line_no, line)`` triples for every ``pii-scan: ignore`` marker."""
    out: list[tuple[str, int, str]] = []
    for path in _git_tracked_files(root):
        if not _allowed(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(path.relative_to(root)) if path.is_absolute() else str(path)
        for line_no, line in enumerate(text.splitlines(), start=1):
            if SUPPRESSION_MARKER in line:
                out.append((rel, line_no, line.strip()))
    return out


# --- Reporting -------------------------------------------------------------


def _truncate(line: str, limit: int = 160) -> str:
    if len(line) <= limit:
        return line
    return line[: limit - 3] + "..."


def format_text(result: ScanResult) -> str:
    lines: list[str] = [f"Scanned {result.files_scanned} files; {len(result.findings)} findings."]
    for severity in (SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW):
        bucket = result.by_severity(severity)
        if not bucket:
            continue
        lines.append("")
        lines.append(f"== {severity.upper()} ({len(bucket)}) ==")
        lines.extend(
            f"  [{finding.rule.name}] {finding.relative_path}:{finding.line_no}: {_truncate(finding.line)}"
            for finding in bucket
        )
    return "\n".join(lines)


def format_markdown(result: ScanResult) -> str:
    lines: list[str] = [
        "# PII / Secret Exposure Scan Report",
        "",
        "Generated by `scripts/pii_scan.py`. This report is regenerated by the",
        "pytest guard in `tests/test_pii_scan.py`; do not hand-edit.",
        "",
        f"- Files scanned: **{result.files_scanned}**",
        f"- Findings (high): **{len(result.by_severity(SEVERITY_HIGH))}**",
        f"- Findings (medium): **{len(result.by_severity(SEVERITY_MEDIUM))}**",
        f"- Findings (low): **{len(result.by_severity(SEVERITY_LOW))}**",
        "",
    ]

    if not result.findings:
        lines.append("No findings. The repository is clean per the configured rules.")
        return "\n".join(lines) + "\n"

    for severity, label in (
        (SEVERITY_HIGH, "High severity"),
        (SEVERITY_MEDIUM, "Medium severity"),
        (SEVERITY_LOW, "Low severity"),
    ):
        bucket = result.by_severity(severity)
        if not bucket:
            continue
        lines.append(f"## {label} ({len(bucket)})")
        lines.append("")
        lines.append("| Rule | Location | Excerpt |")
        lines.append("| --- | --- | --- |")
        for finding in bucket:
            excerpt = _truncate(finding.line).replace("|", r"\|")
            lines.append(f"| `{finding.rule.name}` | `{finding.relative_path}:{finding.line_no}` | `{excerpt}` |")
        lines.append("")

    lines.append("## Rules")
    lines.append("")
    lines.extend(f"- `{rule.name}` — _{rule.severity}_ — {rule.description}" for rule in RULES)
    lines.append("")
    return "\n".join(lines)


def format_full_markdown(result: ScanResult, suppressions: list[tuple[str, int, str]]) -> str:
    """Markdown report including a section enumerating suppression markers."""
    base = format_markdown(result).rstrip("\n")
    if "## Rules" not in base:
        # No findings branch returned early; tack on rules + suppressions.
        rules_section = ["", "## Rules", ""]
        rules_section.extend(f"- `{rule.name}` — _{rule.severity}_ — {rule.description}" for rule in RULES)
        base = base + "\n" + "\n".join(rules_section)

    suppression_lines = ["", "## Reviewed suppressions", ""]
    if not suppressions:
        suppression_lines.append("No `pii-scan: ignore` markers in the repository.")
    else:
        suppression_lines.append(
            "Lines below were reviewed and deliberately suppressed via "
            "`# pii-scan: ignore`. They match scanner rules but are safe in context.",
        )
        suppression_lines.append("")
        suppression_lines.append("| Location | Line |")
        suppression_lines.append("| --- | --- |")
        for rel, line_no, line in suppressions:
            excerpt = _truncate(line).replace("|", r"\|")
            suppression_lines.append(f"| `{rel}:{line_no}` | `{excerpt}` |")
    suppression_lines.append("")
    return base + "\n" + "\n".join(suppression_lines)


# --- CLI -------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--format",
        choices=("text", "markdown"),
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Write a markdown report to this path (implies --format markdown).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Quiet mode: exit non-zero if any high-severity findings are present.",
    )
    args = parser.parse_args(argv)

    result = scan_repo()
    high_count = len(result.by_severity(SEVERITY_HIGH))

    if args.report is not None:
        suppressions = collect_suppressions()
        report = format_full_markdown(result, suppressions)
        args.report.write_text(report, encoding="utf-8")
        if not args.check:
            print(f"Wrote report to {args.report} ({high_count} high-severity findings).")
    elif not args.check:
        output = format_markdown(result) if args.format == "markdown" else format_text(result)
        print(output)

    return 1 if high_count else 0


if __name__ == "__main__":
    sys.exit(main())
