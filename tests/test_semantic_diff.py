"""Tests for scripts/semantic_diff.py (non-LLM logic)."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Load scripts/semantic_diff.py as an importable module
_SPEC_PATH = Path(__file__).parent.parent / "scripts" / "semantic_diff.py"
_spec = importlib.util.spec_from_file_location("semantic_diff", _SPEC_PATH)
assert _spec is not None and _spec.loader is not None
semantic_diff = importlib.util.module_from_spec(_spec)
sys.modules["semantic_diff"] = semantic_diff
_spec.loader.exec_module(semantic_diff)


SAMPLE_DIFF = """diff --git a/foo.py b/foo.py
index 1111111..2222222 100644
--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,3 @@
-old line
+new line
 unchanged
diff --git a/bar.py b/bar.py
index 3333333..4444444 100644
--- a/bar.py
+++ b/bar.py
@@ -10,2 +10,3 @@
 keep
+added
 keep2
"""

BINARY_DIFF = """diff --git a/img.png b/img.png
index 1111111..2222222 100644
Binary files a/img.png and b/img.png differ
"""


def test_build_git_diff_command_default_ref() -> None:
    cmd = semantic_diff.build_git_diff_command(ref="HEAD", range_spec=None, staged=False)
    assert cmd == ["git", "diff", "--no-color", "HEAD"]


def test_build_git_diff_command_staged() -> None:
    cmd = semantic_diff.build_git_diff_command(ref=None, range_spec=None, staged=True)
    assert cmd == ["git", "diff", "--no-color", "--cached"]


def test_build_git_diff_command_range() -> None:
    cmd = semantic_diff.build_git_diff_command(ref=None, range_spec="main..HEAD", staged=False)
    assert cmd == ["git", "diff", "--no-color", "main..HEAD"]


def test_build_git_diff_command_no_args() -> None:
    cmd = semantic_diff.build_git_diff_command(ref=None, range_spec=None, staged=False)
    assert cmd == ["git", "diff", "--no-color"]


def test_split_diff_per_file_separates_chunks() -> None:
    files = semantic_diff.split_diff_per_file(SAMPLE_DIFF)
    assert [f.path for f in files] == ["foo.py", "bar.py"]
    assert all(not f.is_binary for f in files)
    assert "old line" in files[0].body
    assert "added" in files[1].body


def test_split_diff_per_file_empty() -> None:
    assert semantic_diff.split_diff_per_file("") == []
    assert semantic_diff.split_diff_per_file("   \n") == []


def test_split_diff_detects_binary() -> None:
    files = semantic_diff.split_diff_per_file(BINARY_DIFF)
    assert len(files) == 1
    assert files[0].is_binary
    assert files[0].path == "img.png"


def test_truncate_per_file_marks_truncated() -> None:
    big_body = "diff --git a/a b/a\n--- a/a\n+++ b/a\n" + "+x\n" * 5000
    files = semantic_diff.split_diff_per_file(big_body)
    truncated = semantic_diff.truncate_per_file(files, max_bytes=600)
    assert len(truncated) == 1
    assert truncated[0].truncated is True
    assert semantic_diff.TRUNCATION_MARKER.strip() in truncated[0].body
    assert len(truncated[0].body.encode("utf-8")) < 2000


def test_truncate_per_file_skips_small() -> None:
    files = semantic_diff.split_diff_per_file(SAMPLE_DIFF)
    out = semantic_diff.truncate_per_file(files, max_bytes=10_000)
    assert all(not f.truncated for f in out)


def test_truncate_per_file_zero_budget_is_passthrough() -> None:
    files = semantic_diff.split_diff_per_file(SAMPLE_DIFF)
    out = semantic_diff.truncate_per_file(files, max_bytes=0)
    assert out == files


def test_assemble_prompt_diff_replaces_binary_with_note() -> None:
    files = semantic_diff.split_diff_per_file(SAMPLE_DIFF + BINARY_DIFF)
    prompt = semantic_diff.assemble_prompt_diff(files)
    assert "old line" in prompt
    assert "# Binary file: img.png (skipped)" in prompt
    assert "Binary files a/img.png" not in prompt


def test_shape_response_full_payload() -> None:
    raw: dict[str, Any] = {
        "intent": "  Refactor scoring  ",
        "files": [
            {"path": "a.py", "change": "renamed function"},
            {"path": "b.py", "change": ""},
            "not a dict",
        ],
        "risks": ["regression in scorer", "  ", 42],
        "reviewer_focus": ["check tests"],
    }
    result = semantic_diff.shape_response(raw)
    assert result.intent == "Refactor scoring"
    assert result.files == [
        {"path": "a.py", "change": "renamed function"},
        {"path": "b.py", "change": ""},
    ]
    assert result.risks == ["regression in scorer", "42"]
    assert result.reviewer_focus == ["check tests"]


def test_shape_response_handles_missing_keys() -> None:
    result = semantic_diff.shape_response({})
    assert result.intent == "(no summary returned)"
    assert result.files == []
    assert result.risks == []
    assert result.reviewer_focus == []


def test_shape_response_to_dict_roundtrips() -> None:
    raw = {"intent": "x", "files": [{"path": "p", "change": "c"}], "risks": ["r"], "reviewer_focus": ["f"]}
    result = semantic_diff.shape_response(raw)
    assert result.to_dict() == raw


def test_main_empty_diff_exits_zero(monkeypatch, capsys) -> None:
    monkeypatch.setattr(semantic_diff, "run_git_diff", lambda cmd: "")
    rc = semantic_diff.main([])
    assert rc == 0
    captured = capsys.readouterr()
    assert "No diff to explain." in captured.err


def test_main_binary_only_diff_exits_zero(monkeypatch, capsys) -> None:
    monkeypatch.setattr(semantic_diff, "run_git_diff", lambda cmd: BINARY_DIFF)

    def _should_not_call_llm(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("LLM should not be called for binary-only diffs")

    monkeypatch.setattr(semantic_diff, "call_llm", _should_not_call_llm)
    rc = semantic_diff.main(["--no-color"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "binary" in captured.err.lower()


def test_main_json_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(semantic_diff, "run_git_diff", lambda cmd: SAMPLE_DIFF)
    monkeypatch.setattr(
        semantic_diff,
        "call_llm",
        lambda diff_text, model: {
            "intent": "Refactor",
            "files": [{"path": "foo.py", "change": "swapped a line"}],
            "risks": ["regression risk"],
            "reviewer_focus": ["check foo.py"],
        },
    )
    rc = semantic_diff.main(["--json"])
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["intent"] == "Refactor"
    assert payload["files"][0]["path"] == "foo.py"
    assert payload["risks"] == ["regression risk"]
    assert payload["reviewer_focus"] == ["check foo.py"]


def test_main_truncation_notice(monkeypatch, capsys) -> None:
    big_body = "diff --git a/a b/a\n--- a/a\n+++ b/a\n" + "+x\n" * 5000
    monkeypatch.setattr(semantic_diff, "run_git_diff", lambda cmd: big_body)
    monkeypatch.setattr(
        semantic_diff,
        "call_llm",
        lambda diff_text, model: {"intent": "x", "files": [], "risks": [], "reviewer_focus": []},
    )
    rc = semantic_diff.main(["--max-bytes", "500", "--no-color"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "truncated" in captured.err.lower()


def test_main_git_failure_returns_two(monkeypatch, capsys) -> None:
    def _raise(cmd: list[str]) -> str:
        raise RuntimeError("git diff failed: bad ref")

    monkeypatch.setattr(semantic_diff, "run_git_diff", _raise)
    rc = semantic_diff.main(["--ref", "nonexistent"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "git diff failed" in captured.err


def test_run_git_diff_invokes_subprocess(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeProc:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = "out"
            self.stderr = ""

    def _fake_run(cmd, capture_output, text, check):
        captured["cmd"] = cmd
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["check"] = check
        return _FakeProc()

    monkeypatch.setattr(semantic_diff.subprocess, "run", _fake_run)
    out = semantic_diff.run_git_diff(["git", "diff"])
    assert out == "out"
    assert captured["cmd"] == ["git", "diff"]
    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["check"] is False


def test_run_git_diff_raises_on_failure(monkeypatch) -> None:
    class _FakeProc:
        returncode = 128
        stdout = ""
        stderr = "fatal: bad ref\n"

    monkeypatch.setattr(semantic_diff.subprocess, "run", lambda *a, **k: _FakeProc())
    with pytest.raises(RuntimeError, match="git diff failed"):
        semantic_diff.run_git_diff(["git", "diff", "bogus"])


def test_render_rich_no_color_smoke() -> None:
    # Smoke test: rendering should not raise even with empty optional fields
    result = semantic_diff.SemanticDiffResult(
        intent="Test intent",
        files=[{"path": "a.py", "change": "did a thing"}],
        risks=["something"],
        reviewer_focus=["check it"],
    )
    # Capture stdout to keep test output tidy
    buf = io.StringIO()
    sys_stdout = sys.stdout
    sys.stdout = buf
    try:
        semantic_diff.render_rich(result, no_color=True)
    finally:
        sys.stdout = sys_stdout
    output = buf.getvalue()
    assert "Test intent" in output
    assert "a.py" in output
