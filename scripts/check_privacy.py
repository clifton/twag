#!/usr/bin/env python3
"""Privacy policy consistency checker.

Scans the twag codebase and validates that PRIVACY.md accurately documents:
1. External service calls (HTTP, subprocess)
2. Database tables
3. Credential environment variables
4. Web API endpoints
5. Personal data logging
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRIVACY_MD = REPO_ROOT / "PRIVACY.md"
SRC_DIR = REPO_ROOT / "twag"


def read_privacy_policy() -> str:
    """Read and return the privacy policy text."""
    if not PRIVACY_MD.exists():
        print("FAIL: PRIVACY.md not found at repo root")
        sys.exit(1)
    return PRIVACY_MD.read_text()


def collect_python_files() -> list[Path]:
    """Collect all Python source files under twag/, excluding vendored code."""
    return sorted(p for p in SRC_DIR.rglob("*.py") if ".venv" not in p.parts and "__pycache__" not in p.parts)


# ---------------------------------------------------------------------------
# 1. External service calls
# ---------------------------------------------------------------------------

EXTERNAL_CALL_PATTERNS: dict[str, list[str]] = {
    "Telegram API": [r"api\.telegram\.org"],
    "Anthropic API": [r"anthropic", r"client\.messages\.create"],
    "Google Gemini API": [r"google\.genai", r"models\.generate_content"],
    "bird CLI": [r"subprocess\.run\(.*bird", r'\["bird"'],
    "URL Expansion": [r"urllib\.request\.urlopen", r"urlopen\("],
}


def check_external_calls(policy: str, files: list[Path]) -> list[str]:
    """Verify external service calls are documented in the policy."""
    issues: list[str] = []
    for service, patterns in EXTERNAL_CALL_PATTERNS.items():
        found_in_code = False
        for f in files:
            text = f.read_text(errors="replace")
            if any(re.search(p, text) for p in patterns):
                found_in_code = True
                break
        if found_in_code and service not in policy:
            issues.append(f"External service '{service}' found in code but not in PRIVACY.md")
        if not found_in_code and service in policy:
            issues.append(f"External service '{service}' documented in PRIVACY.md but not found in code")
    return issues


# ---------------------------------------------------------------------------
# 2. Database tables
# ---------------------------------------------------------------------------

TABLE_PATTERN = re.compile(r"CREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", re.IGNORECASE)

# Words that are clearly not table names (matched from comments/docs)
TABLE_FALSE_POSITIVES = {"may", "a", "the", "an", "this", "that", "it", "or", "and"}


def check_database_tables(policy: str, files: list[Path]) -> list[str]:
    """Verify all database tables are documented in the policy."""
    issues: list[str] = []
    code_tables: set[str] = set()
    for f in files:
        text = f.read_text(errors="replace")
        code_tables.update(TABLE_PATTERN.findall(text))
    code_tables -= TABLE_FALSE_POSITIVES

    issues.extend(
        f"Database table '{table}' found in code but not in PRIVACY.md"
        for table in sorted(code_tables)
        if table not in policy
    )

    return issues


# ---------------------------------------------------------------------------
# 3. Credential environment variables
# ---------------------------------------------------------------------------

CREDENTIAL_VARS = [
    "AUTH_TOKEN",
    "CT0",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]

ENV_VAR_PATTERN = re.compile(r'(?:os\.environ|os\.getenv|environ\.get)\s*[\[(]\s*["\'](\w+)["\']')


def check_credentials(policy: str, files: list[Path]) -> list[str]:
    """Verify credential env vars are documented in the policy."""
    issues: list[str] = []
    code_env_vars: set[str] = set()
    for f in files:
        text = f.read_text(errors="replace")
        code_env_vars.update(ENV_VAR_PATTERN.findall(text))

    # Also pick up vars from auth.py patterns like env_data.get("AUTH_TOKEN")
    auth_pattern = re.compile(r'\.get\(\s*["\'](\w+(?:_KEY|_TOKEN|_ID|_SECRET)\w*)["\']')
    for f in files:
        text = f.read_text(errors="replace")
        code_env_vars.update(auth_pattern.findall(text))

    # Check that known credential vars found in code are documented
    issues.extend(
        f"Credential '{var}' used in code but not in PRIVACY.md"
        for var in CREDENTIAL_VARS
        if var in code_env_vars and var not in policy
    )

    # Check for undocumented credential-like vars
    credential_suffixes = ("_KEY", "_TOKEN", "_SECRET")
    issues.extend(
        f"Credential-like env var '{var}' found in code but not in PRIVACY.md"
        for var in sorted(code_env_vars)
        if any(var.endswith(s) for s in credential_suffixes) and var not in policy
    )

    return issues


# ---------------------------------------------------------------------------
# 4. Web API endpoints
# ---------------------------------------------------------------------------

ROUTE_PATTERN = re.compile(r'@\w+\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']', re.IGNORECASE)


def check_web_endpoints(policy: str, files: list[Path]) -> list[str]:
    """Verify web API endpoints are documented in the policy."""
    issues: list[str] = []
    web_dir = SRC_DIR / "web"
    if not web_dir.exists():
        return issues

    route_files = sorted(web_dir.rglob("*.py"))
    code_endpoints: set[tuple[str, str]] = set()
    for f in route_files:
        text = f.read_text(errors="replace")
        for match in ROUTE_PATTERN.finditer(text):
            method = match.group(1).upper()
            path = match.group(2)
            code_endpoints.add((method, path))

    for method, path in sorted(code_endpoints):
        # Normalize path parameters for matching: /tweets/{tweet_id} style
        normalized = re.sub(r"\{[^}]+\}", r"{...}", path)
        policy_normalized = re.sub(r"\{[^}]+\}", r"{...}", policy)
        if path not in policy and normalized not in policy_normalized:
            issues.append(f"Web endpoint {method} {path} found in code but not in PRIVACY.md")

    return issues


# ---------------------------------------------------------------------------
# 5. Personal data logging
# ---------------------------------------------------------------------------

PERSONAL_DATA_LOG_PATTERNS = [
    (r"log\.\w+\(.*author_handle", "author_handle in log statement"),
    (r"log\.\w+\(.*\bcontent\b", "tweet content in log statement"),
    (r"log\.\w+\(.*\busername\b", "username in log statement"),
    (r"log\.\w+\(.*\bdisplay_name\b", "display_name in log statement"),
]


def check_personal_data_logging(files: list[Path]) -> list[str]:
    """Check for personal data appearing in log statements."""
    issues: list[str] = []
    for f in files:
        text = f.read_text(errors="replace")
        for line_num, line in enumerate(text.splitlines(), 1):
            for pattern, description in PERSONAL_DATA_LOG_PATTERNS:
                if re.search(pattern, line):
                    issues.append(f"{f.relative_to(REPO_ROOT)}:{line_num}: {description}")
    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run all privacy consistency checks."""
    policy = read_privacy_policy()
    files = collect_python_files()

    all_issues: list[str] = []

    checks = [
        ("External service calls", check_external_calls(policy, files)),
        ("Database tables", check_database_tables(policy, files)),
        ("Credentials", check_credentials(policy, files)),
        ("Web API endpoints", check_web_endpoints(policy, files)),
        ("Personal data logging", check_personal_data_logging(files)),
    ]

    for name, issues in checks:
        if issues:
            print(f"\n{'=' * 60}")
            print(f"ISSUES: {name}")
            print(f"{'=' * 60}")
            for issue in issues:
                print(f"  - {issue}")
            all_issues.extend(issues)
        else:
            print(f"OK: {name}")

    if all_issues:
        print(f"\n{len(all_issues)} issue(s) found.")
        return 1

    print("\nAll privacy checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
