#!/usr/bin/env python3
"""Detect documentation that's out of sync with code.

Concrete, machine-verifiable checks against the live codebase:

1. CLI commands documented in README.md / CLAUDE.md / SKILL.md exist as
   registered Click commands.
2. Every registered Click command appears in at least one doc.
3. Packages listed under "Core packages" in CLAUDE.md exist as
   ``twag/<name>/`` directories.
4. Env vars in ``SKILL.md`` ``openclaw.requires.env`` are referenced in code.
5. Files in CLAUDE.md's "Key Files" table exist on disk.

Usage::

    python scripts/check_doc_drift.py

Exits non-zero if drift is detected. Designed for CI.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import click

REPO_ROOT = Path(__file__).resolve().parent.parent

# CLI commands that appear in code but are intentionally undocumented or
# considered internal. Keep this list small and justified.
CLI_DOC_EXEMPT: set[str] = {
    "metrics",  # internal observability command, not user-facing
}


@dataclass
class CheckResult:
    name: str
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def collect_cli_commands() -> set[str]:
    """Walk the registered Click command tree and return full command paths.

    Includes the root command names and ``group sub`` paths. Aliases (if any)
    are included. The Click CLI is imported from ``twag.cli``.
    """
    sys.path.insert(0, str(REPO_ROOT))
    from twag.cli import cli as root

    found: set[str] = set()

    def walk(group: click.Group, prefix: str = "") -> None:
        for name, cmd in group.commands.items():
            full = f"{prefix} {name}".strip()
            found.add(full)
            if isinstance(cmd, click.Group):
                walk(cmd, full)

    walk(root)
    return found


_FENCED_BLOCK_RE = re.compile(r"```[a-zA-Z0-9_-]*\n(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


def _code_spans(text: str) -> list[str]:
    """Return all inline-code and fenced-code spans from a markdown doc.

    Prose mentions of the word ``twag`` (the project name) live outside code,
    so only command-shaped references inside code spans should be treated as
    claims about the CLI surface.
    """
    spans: list[str] = []
    spans.extend(_FENCED_BLOCK_RE.findall(text))
    spans.extend(_INLINE_CODE_RE.findall(text))
    return spans


def _doc_command_mentions(text: str) -> set[str]:
    """Return command paths plausibly referenced in docs.

    Matches ``twag <name>`` and ``twag <group> <sub>`` only — does not try to
    parse flag-laden examples. Only looks inside code spans to avoid matching
    prose like "twag is a Twitter aggregator".
    """
    mentions: set[str] = set()
    for span in _code_spans(text):
        for match in re.finditer(r"\btwag[ \t]+([a-z][a-z0-9_-]*)(?:[ \t]+([a-z][a-z0-9_-]*))?", span):
            first = match.group(1)
            second = match.group(2)
            mentions.add(first)
            if second:
                mentions.add(f"{first} {second}")
    return mentions


def check_documented_commands_exist(docs: dict[str, str], cli_commands: set[str]) -> CheckResult:
    """Every ``twag <cmd>`` group/sub mentioned in docs must exist."""
    result = CheckResult("documented commands resolve to real CLI commands")
    # Top-level command names — used to filter false positives like
    # "twag init --force" where the second token is a flag, not a sub.
    top_level = {c for c in cli_commands if " " not in c}
    for doc_name, text in docs.items():
        for mention in sorted(_doc_command_mentions(text)):
            tokens = mention.split()
            # Single-token mention must be a top-level command
            if len(tokens) == 1:
                if mention not in top_level:
                    result.issues.append(f"{doc_name}: references `twag {mention}` but no such command is registered")
                continue
            # Two-token mention: only flag if the first token is a known group
            group, sub = tokens
            group_cmd = _resolve_group(group, cli_commands)
            if group_cmd is None:
                continue  # not a known group, skip (likely a flag)
            if mention not in cli_commands:
                # Check if `sub` is plausibly a flag-like token
                if sub.startswith("-"):
                    continue
                result.issues.append(
                    f"{doc_name}: references `twag {mention}` but `{sub}` is not a subcommand of `{group}`",
                )
    return result


def _resolve_group(name: str, cli_commands: set[str]) -> str | None:
    """Return *name* if there is at least one ``name <sub>`` entry."""
    if any(c.startswith(f"{name} ") for c in cli_commands):
        return name
    return None


def check_cli_commands_documented(docs: dict[str, str], cli_commands: set[str]) -> CheckResult:
    """Every registered command should appear in README.md or SKILL.md."""
    result = CheckResult("registered CLI commands appear in docs")
    user_facing_docs = {k: v for k, v in docs.items() if k in {"README.md", "SKILL.md"}}
    combined = "\n".join(user_facing_docs.values())
    for command in sorted(cli_commands):
        if command in CLI_DOC_EXEMPT:
            continue
        # Match `twag <command>` allowing the full path.
        pattern = rf"\btwag\s+{re.escape(command)}\b"
        if not re.search(pattern, combined):
            result.issues.append(f"command `twag {command}` is registered but not documented in README.md or SKILL.md")
    return result


CORE_PACKAGES_HEADER = "**Core packages:**"


def parse_core_packages(claude_md: str) -> list[str]:
    """Extract package paths claimed in CLAUDE.md's 'Core packages' bullet list.

    Returns directory-style entries like ``twag/cli/`` (trailing slash retained
    when present). Files listed in the bullet list (e.g. ``twag/auth.py``) are
    skipped — only directory packages are checked here.
    """
    if CORE_PACKAGES_HEADER not in claude_md:
        return []
    section = claude_md.split(CORE_PACKAGES_HEADER, 1)[1]
    # Stop at next blank-line + non-bullet boundary (next ## section, etc.)
    end_match = re.search(r"\n\n##\s", section)
    if end_match:
        section = section[: end_match.start()]
    paths: list[str] = []
    for line in section.splitlines():
        m = re.match(r"\s*-\s+`([^`]+)`", line)
        if not m:
            continue
        path = m.group(1)
        if path.endswith("/"):
            paths.append(path)
    return paths


def check_core_packages_exist(claude_md: str) -> CheckResult:
    result = CheckResult("CLAUDE.md 'Core packages' entries exist as directories")
    for path in parse_core_packages(claude_md):
        full = REPO_ROOT / path
        if not full.is_dir():
            result.issues.append(f"CLAUDE.md lists `{path}` as a core package but {full} is not a directory")
    return result


def parse_skill_env_vars(skill_md: str) -> list[str]:
    """Extract env var names from SKILL.md openclaw.requires.env list."""
    m = re.search(r"requires:\s*\n(?:\s+bins:\s*\[[^\]]*\]\s*\n)?\s+env:\s*\[([^\]]*)\]", skill_md)
    if not m:
        return []
    raw = m.group(1)
    return re.findall(r'"([A-Z_][A-Z0-9_]*)"', raw)


def check_skill_env_vars_referenced(skill_md: str) -> CheckResult:
    result = CheckResult("SKILL.md env vars are referenced in twag/")
    env_vars = parse_skill_env_vars(skill_md)
    if not env_vars:
        result.issues.append("could not parse openclaw.requires.env from SKILL.md")
        return result
    py_files = list((REPO_ROOT / "twag").rglob("*.py"))
    contents = "\n".join(_read(p) for p in py_files)
    for var in env_vars:
        if var not in contents:
            result.issues.append(f"SKILL.md declares env var `{var}` but no twag/*.py references it")
    return result


def parse_key_files_table(claude_md: str) -> list[str]:
    """Extract file paths from CLAUDE.md's 'Key Files' table."""
    m = re.search(r"##\s+Key Files\s*\n(.*?)(?:\n##\s|\Z)", claude_md, re.DOTALL)
    if not m:
        return []
    table = m.group(1)
    paths: list[str] = []
    for line in table.splitlines():
        # Markdown table row: | `path` | description |
        cell = re.match(r"\s*\|\s*`([^`]+)`\s*\|", line)
        if cell:
            paths.append(cell.group(1))
    return paths


def check_key_files_exist(claude_md: str) -> CheckResult:
    result = CheckResult("CLAUDE.md 'Key Files' entries exist on disk")
    for path in parse_key_files_table(claude_md):
        full = REPO_ROOT / path
        if not full.exists():
            result.issues.append(f"CLAUDE.md lists `{path}` in Key Files but {full} does not exist")
    return result


def run_all_checks() -> list[CheckResult]:
    docs = {
        "README.md": _read(REPO_ROOT / "README.md"),
        "CLAUDE.md": _read(REPO_ROOT / "CLAUDE.md"),
        "SKILL.md": _read(REPO_ROOT / "SKILL.md"),
        "INSTALL.md": _read(REPO_ROOT / "INSTALL.md"),
    }
    cli_commands = collect_cli_commands()
    return [
        check_cli_commands_documented(docs, cli_commands),
        check_documented_commands_exist(docs, cli_commands),
        check_core_packages_exist(docs["CLAUDE.md"]),
        check_skill_env_vars_referenced(docs["SKILL.md"]),
        check_key_files_exist(docs["CLAUDE.md"]),
    ]


def format_report(results: list[CheckResult]) -> str:
    lines: list[str] = []
    for r in results:
        marker = "OK" if r.ok else "FAIL"
        lines.append(f"[{marker}] {r.name}")
        lines.extend(f"    - {issue}" for issue in r.issues)
    total = sum(len(r.issues) for r in results)
    lines.append("")
    lines.append(f"{total} drift issue(s) detected" if total else "No drift detected")
    return "\n".join(lines)


def main() -> int:
    results = run_all_checks()
    print(format_report(results))
    return 1 if any(not r.ok for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
