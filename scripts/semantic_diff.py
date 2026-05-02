#!/usr/bin/env python3
"""Semantic diff explainer.

Generates a structured, human-readable explanation of the semantic intent
behind a git diff using the repo's existing Anthropic LLM client.

Usage:
    scripts/semantic_diff.py                    # diff HEAD against the working tree
    scripts/semantic_diff.py --ref HEAD~3       # diff between HEAD~3 and HEAD
    scripts/semantic_diff.py --range main..HEAD # diff between two refs
    scripts/semantic_diff.py --staged           # diff staged changes
    scripts/semantic_diff.py --json             # emit raw JSON for scripting
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_BYTES = 60_000
TRUNCATION_MARKER = "\n... [truncated for length] ...\n"

PROMPT_TEMPLATE = """You are an expert code reviewer. Below is a git diff. Explain the semantic
meaning of these changes — focus on intent and behavior, not a line-by-line description.

Return ONLY a JSON object with this exact shape:

{{
  "intent": "1-2 sentence summary of the overall goal of the change",
  "files": [
    {{
      "path": "path/to/file",
      "change": "what behavior changed in this file (1-3 sentences)"
    }}
  ],
  "risks": ["risk or regression area 1", "risk or regression area 2"],
  "reviewer_focus": ["thing reviewers should pay close attention to"]
}}

If a list has no entries, return an empty array. Do not include any prose
outside the JSON object.

DIFF:
{diff}
"""


@dataclass
class FileDiff:
    path: str
    body: str
    is_binary: bool = False
    truncated: bool = False


@dataclass
class SemanticDiffResult:
    intent: str
    files: list[dict[str, str]] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    reviewer_focus: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "files": self.files,
            "risks": self.risks,
            "reviewer_focus": self.reviewer_focus,
        }


def build_git_diff_command(
    *,
    ref: str | None,
    range_spec: str | None,
    staged: bool,
) -> list[str]:
    """Return the argv for `git diff` based on the requested mode.

    Mutually exclusive flags are validated by argparse; this only chooses the form.
    """
    cmd = ["git", "diff", "--no-color"]
    if staged:
        cmd.append("--cached")
    elif range_spec:
        cmd.append(range_spec)
    elif ref:
        cmd.append(ref)
    return cmd


def run_git_diff(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"git diff failed: {proc.stderr.strip()}")
    return proc.stdout


def split_diff_per_file(diff_text: str) -> list[FileDiff]:
    """Split a unified git diff into per-file chunks.

    Each chunk starts with a `diff --git` header. Binary files (detected by
    `Binary files ... differ` markers) are flagged so they can be skipped.
    """
    if not diff_text.strip():
        return []

    lines = diff_text.splitlines(keepends=True)
    chunks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("diff --git "):
            if current:
                chunks.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        chunks.append(current)

    files: list[FileDiff] = []
    for chunk in chunks:
        header = chunk[0]
        path = _parse_path_from_header(header)
        body = "".join(chunk)
        is_binary = "Binary files " in body and " differ" in body
        files.append(FileDiff(path=path, body=body, is_binary=is_binary))
    return files


def _parse_path_from_header(header: str) -> str:
    """Pull a stable file path from a `diff --git a/<path> b/<path>` line."""
    parts = header.strip().split()
    for part in parts:
        if part.startswith("b/"):
            return part[2:]
    if len(parts) >= 4:
        return parts[-1].lstrip("b/")
    return "<unknown>"


def truncate_per_file(files: list[FileDiff], max_bytes: int) -> list[FileDiff]:
    """Truncate each file's diff body so the combined size stays under max_bytes.

    Distributes the budget evenly across non-binary files. Binary file entries
    keep their (already short) marker text. Files that get cut have a truncation
    marker appended and `truncated=True`.
    """
    if max_bytes <= 0:
        return files

    text_files = [f for f in files if not f.is_binary]
    if not text_files:
        return files

    per_file_budget = max(500, max_bytes // max(len(text_files), 1))
    out: list[FileDiff] = []
    for f in files:
        if f.is_binary:
            out.append(f)
            continue
        encoded = f.body.encode("utf-8")
        if len(encoded) <= per_file_budget:
            out.append(f)
            continue
        truncated_body = encoded[:per_file_budget].decode("utf-8", errors="ignore")
        truncated_body = truncated_body + TRUNCATION_MARKER
        out.append(FileDiff(path=f.path, body=truncated_body, is_binary=False, truncated=True))
    return out


def assemble_prompt_diff(files: list[FileDiff]) -> str:
    """Concatenate per-file diffs, skipping binary-only chunks with a note."""
    parts: list[str] = []
    for f in files:
        if f.is_binary:
            parts.append(f"# Binary file: {f.path} (skipped)\n")
            continue
        parts.append(f.body)
    return "".join(parts)


def shape_response(raw: dict[str, Any]) -> SemanticDiffResult:
    """Normalize an LLM JSON response into a SemanticDiffResult.

    Tolerates missing keys and coerces string lists where present so that
    downstream rendering does not need to defensively unpack.
    """
    intent = str(raw.get("intent", "")).strip() or "(no summary returned)"
    files_raw = raw.get("files") or []
    files: list[dict[str, str]] = []
    if isinstance(files_raw, list):
        for entry in files_raw:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path", "")).strip()
            change = str(entry.get("change", "")).strip()
            if path or change:
                files.append({"path": path or "(unknown)", "change": change})
    risks = _coerce_string_list(raw.get("risks"))
    reviewer_focus = _coerce_string_list(raw.get("reviewer_focus"))
    return SemanticDiffResult(
        intent=intent,
        files=files,
        risks=risks,
        reviewer_focus=reviewer_focus,
    )


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def call_llm(diff_text: str, *, model: str) -> dict[str, Any]:
    """Send the prompt to Anthropic and parse the JSON response."""
    from twag.scorer import _parse_json_response, get_anthropic_client

    client = get_anthropic_client()
    prompt = PROMPT_TEMPLATE.format(diff=diff_text)
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [getattr(b, "text", "") for b in response.content]
    text = next((t for t in text_blocks if isinstance(t, str) and t.strip()), "")
    parsed = _parse_json_response(text)
    if isinstance(parsed, list):
        return {"intent": "", "files": [], "risks": [], "reviewer_focus": []}
    return parsed


def render_rich(result: SemanticDiffResult, *, no_color: bool) -> None:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console(no_color=no_color, color_system=None if no_color else "auto")
    console.print(Panel(result.intent, title="Intent", border_style="cyan"))

    if result.files:
        table = Table(title="Per-file changes", show_lines=False)
        table.add_column("File", style="bold")
        table.add_column("Change")
        for entry in result.files:
            table.add_row(entry.get("path", ""), entry.get("change", ""))
        console.print(table)

    if result.risks:
        body = "\n".join(f"• {r}" for r in result.risks)
        console.print(Panel(body, title="Risks / regression areas", border_style="red"))

    if result.reviewer_focus:
        body = "\n".join(f"• {r}" for r in result.reviewer_focus)
        console.print(Panel(body, title="Reviewer focus", border_style="yellow"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Semantic diff explainer using the twag LLM client")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ref", help="Single git ref to diff against the working tree (default: HEAD)")
    mode.add_argument("--range", dest="range_spec", help="Git range, e.g. main..HEAD")
    mode.add_argument("--staged", action="store_true", help="Diff staged changes (git diff --cached)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Anthropic model name")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help="Truncate the combined diff to roughly this many bytes",
    )
    parser.add_argument("--json", dest="as_json", action="store_true", help="Emit raw JSON instead of Rich output")
    parser.add_argument("--no-color", action="store_true", help="Disable colored Rich output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ref = args.ref or (None if (args.range_spec or args.staged) else "HEAD")
    cmd = build_git_diff_command(ref=ref, range_spec=args.range_spec, staged=args.staged)

    try:
        diff_text = run_git_diff(cmd)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    files = split_diff_per_file(diff_text)
    if not files:
        print("No diff to explain.", file=sys.stderr)
        return 0

    if all(f.is_binary for f in files):
        print("Diff contains only binary changes; nothing to explain.", file=sys.stderr)
        return 0

    files = truncate_per_file(files, args.max_bytes)
    truncated_paths = [f.path for f in files if f.truncated]
    if truncated_paths and not args.as_json:
        print(
            f"Notice: truncated {len(truncated_paths)} file(s) to fit within {args.max_bytes} bytes.",
            file=sys.stderr,
        )

    prompt_diff = assemble_prompt_diff(files)

    raw = call_llm(prompt_diff, model=args.model)
    result = shape_response(raw)

    if args.as_json:
        json.dump(result.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    render_rich(result, no_color=args.no_color)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
