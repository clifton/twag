"""Regression guard: the PII scanner must report zero high-severity findings.

This keeps secrets, credential literals, and risky logging from sneaking back
into the tree.  Medium and low findings are reported but do not fail CI.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCANNER_PATH = REPO_ROOT / "scripts" / "pii_scan.py"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("twag_pii_scan", SCANNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("twag_pii_scan", module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scanner():
    return _load_scanner()


def test_repo_has_no_high_severity_pii(scanner) -> None:
    result = scanner.scan_repo()
    high = result.by_severity(scanner.SEVERITY_HIGH)
    if high:
        formatted = "\n".join(f"  {f.rule.name} {f.relative_path}:{f.line_no}: {f.line[:160]}" for f in high)
        pytest.fail("scripts/pii_scan.py reported high-severity findings:\n" + formatted)


def test_scanner_detects_known_secret_patterns(scanner, tmp_path: Path) -> None:
    """Sanity-check the rules trip on known-bad payloads when fed synthetic input."""
    work = tmp_path / "src"
    work.mkdir()
    sample = work / "leak.py"
    sample.write_text(
        "\n".join(
            [
                'GEMINI = "AIza' + "A" * 35 + '"',
                'OPENAI = "sk-' + "A" * 40 + '"',
                'GH = "ghp_' + "A" * 36 + '"',
                'TG = "1234567890:' + "A" * 35 + '"',
                'AUTH_TOKEN = "' + "f" * 40 + '"',
            ],
        ),
        encoding="utf-8",
    )

    result = scanner.scan_paths([sample])
    rule_names = {f.rule.name for f in result.findings}
    assert {
        "google_api_key",
        "openai_api_key",
        "github_token",
        "telegram_bot_token",
        "twitter_auth_token_assignment",
    }.issubset(rule_names), rule_names


def test_scanner_respects_suppression_marker(scanner, tmp_path: Path) -> None:
    sample = tmp_path / "ok.py"
    sample.write_text(
        'GEMINI = "AIza' + "A" * 35 + '"  # pii-scan: ignore\n',
        encoding="utf-8",
    )
    result = scanner.scan_paths([sample])
    assert result.findings == []


def test_scanner_skips_test_paths_by_default(scanner, tmp_path: Path) -> None:
    """Risky-log rules should not flag fixtures under tests/."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    sample = tests_dir / "test_dummy.py"
    sample.write_text('print(f"token={auth_token}")\n', encoding="utf-8")

    monkey_root = tmp_path
    # Re-target the scanner at a synthetic root via scan_paths instead of scan_repo
    # so we exercise the test-path skip logic without touching the real repo.
    original_root = scanner.REPO_ROOT
    scanner.REPO_ROOT = monkey_root
    try:
        result = scanner.scan_paths([sample])
    finally:
        scanner.REPO_ROOT = original_root

    risky = [f for f in result.findings if f.rule.name == "risky_log_of_secret"]
    assert risky == []
