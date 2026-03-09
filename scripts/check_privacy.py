#!/usr/bin/env python3
"""Privacy policy consistency checker.

Scans the twag codebase and verifies that PRIVACY.md accurately documents:
1. External HTTP/API calls
2. Database tables storing personal data
3. Credential environment variables
4. Web API endpoints
5. Logging of personal data

Exit code 0 = all checks pass, 1 = discrepancies found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRIVACY_MD = REPO_ROOT / "PRIVACY.md"
TWAG_SRC = REPO_ROOT / "twag"


def _read_privacy() -> str:
    return PRIVACY_MD.read_text()


def _python_files() -> list[Path]:
    return sorted(TWAG_SRC.rglob("*.py"))


# ---------------------------------------------------------------------------
# 1. External service calls
# ---------------------------------------------------------------------------

# Patterns that indicate outbound network calls
_EXTERNAL_CALL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("httpx", re.compile(r"httpx\.(get|post|put|patch|delete|head)\s*\(")),
    ("httpx_client", re.compile(r"httpx\.(?:Client|AsyncClient)\s*\(")),
    ("urlopen", re.compile(r"urlopen\s*\(")),
    ("anthropic", re.compile(r"(?:client|self\._client)\.messages\.create\s*\(")),
    ("gemini", re.compile(r"(?:client|self\._client)\.models\.generate_content\s*\(")),
    ("requests", re.compile(r"requests\.(get|post|put|patch|delete|head)\s*\(")),
    ("aiohttp", re.compile(r"session\.(get|post|put|patch|delete|head)\s*\(")),
    ("subprocess_bird", re.compile(r"subprocess\.run\s*\(\s*\[.*bird")),
]

# Services that must be documented in PRIVACY.md
_REQUIRED_SERVICES = {
    "httpx": "httpx",
    "httpx_client": "httpx",
    "urlopen": "Link Expansion",
    "anthropic": "Anthropic",
    "gemini": "Gemini",
    "requests": "requests",
    "aiohttp": "aiohttp",
    "subprocess_bird": "bird",
}

_SERVICE_PRIVACY_KEYWORDS = {
    "httpx": ["telegram", "api.telegram.org", "image", "pbs.twimg"],
    "urlopen": ["t.co", "link expansion", "expand"],
    "anthropic": ["anthropic", "anthropic api"],
    "gemini": ["gemini", "google"],
    "requests": ["requests"],
    "aiohttp": ["aiohttp"],
    "subprocess_bird": ["bird", "twitter", "auth_token", "ct0"],
}


def check_external_calls(privacy_text: str) -> list[str]:
    """Verify all external call sites are documented."""
    issues: list[str] = []
    privacy_lower = privacy_text.lower()

    found_services: dict[str, list[str]] = {}

    for pyfile in _python_files():
        # Skip test files
        if "test" in pyfile.name:
            continue
        content = pyfile.read_text()
        rel = pyfile.relative_to(REPO_ROOT)
        for svc_key, pattern in _EXTERNAL_CALL_PATTERNS:
            if pattern.search(content):
                found_services.setdefault(svc_key, []).append(str(rel))

    for svc_key, files in found_services.items():
        keywords = _SERVICE_PRIVACY_KEYWORDS.get(svc_key, [])
        if not any(kw in privacy_lower for kw in keywords):
            label = _REQUIRED_SERVICES[svc_key]
            issues.append(f"External call type '{label}' found in {', '.join(files)} but not documented in PRIVACY.md")

    return issues


# ---------------------------------------------------------------------------
# 2. Database tables
# ---------------------------------------------------------------------------

_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
    re.IGNORECASE,
)


def check_db_tables(privacy_text: str) -> list[str]:
    """Verify all DB tables are listed in PRIVACY.md."""
    issues: list[str] = []
    privacy_lower = privacy_text.lower()

    schema_files = list(TWAG_SRC.rglob("schema*.py")) + list(TWAG_SRC.rglob("*.sql"))

    tables_found: set[str] = set()
    for sf in schema_files:
        content = sf.read_text()
        for m in _CREATE_TABLE_RE.finditer(content):
            tables_found.add(m.group(1).lower())

    issues.extend(
        f"Database table '{table}' not documented in PRIVACY.md"
        for table in sorted(tables_found)
        if table not in privacy_lower
    )

    return issues


# ---------------------------------------------------------------------------
# 3. Credential env vars
# ---------------------------------------------------------------------------

_KNOWN_CRED_PATTERNS = [
    re.compile(r"""(?:os\.environ|os\.getenv|get_api_key)\s*[\[(]\s*["'](\w+_(?:KEY|TOKEN|SECRET|ID))["']"""),
    re.compile(r"""["'](AUTH_TOKEN|CT0)["']"""),
    re.compile(r"""["'](TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)["']"""),
]


def check_credentials(privacy_text: str) -> list[str]:
    """Verify all credential env vars are documented."""
    issues: list[str] = []
    privacy_upper = privacy_text.upper()

    creds_found: dict[str, list[str]] = {}

    for pyfile in _python_files():
        if "test" in pyfile.name:
            continue
        content = pyfile.read_text()
        rel = pyfile.relative_to(REPO_ROOT)
        for pattern in _KNOWN_CRED_PATTERNS:
            for m in pattern.finditer(content):
                var_name = m.group(1)
                creds_found.setdefault(var_name, []).append(str(rel))

    for var_name, files in sorted(creds_found.items()):
        if var_name not in privacy_upper:
            issues.append(f"Credential '{var_name}' used in {', '.join(files)} but not documented in PRIVACY.md")

    return issues


# ---------------------------------------------------------------------------
# 4. Web API endpoints
# ---------------------------------------------------------------------------

_ROUTE_DECORATOR_RE = re.compile(
    r"""@(?:router|app)\.(get|post|put|delete|patch|head|options)\s*\(\s*["']([^"']+)["']"""
)


def check_web_endpoints(privacy_text: str) -> list[str]:
    """Verify all web API endpoints are documented."""
    issues: list[str] = []

    web_dir = TWAG_SRC / "web"
    if not web_dir.exists():
        return issues

    endpoints_found: list[tuple[str, str, str]] = []

    for pyfile in web_dir.rglob("*.py"):
        content = pyfile.read_text()
        rel = pyfile.relative_to(REPO_ROOT)
        for m in _ROUTE_DECORATOR_RE.finditer(content):
            method = m.group(1).upper()
            path = m.group(2)
            endpoints_found.append((method, path, str(rel)))

    for method, path, source in endpoints_found:
        # Normalize path for matching — replace {param} with a pattern
        # that matches the PRIVACY.md table format
        search_path = re.sub(r"\{[^}]+\}", r"{", path)
        # Check if the path appears in the privacy doc
        if path not in privacy_text and search_path.rstrip("{") not in privacy_text:
            # Try a looser match: just the path without params
            base_path = re.sub(r"/\{[^}]+\}", "", path)
            if base_path not in privacy_text:
                issues.append(f"Endpoint {method} {path} (in {source}) not documented in PRIVACY.md")

    return issues


# ---------------------------------------------------------------------------
# 5. Logging of personal data
# ---------------------------------------------------------------------------

_PERSONAL_DATA_LOG_RE = re.compile(
    r"""(?:log(?:ger)?\.(?:info|warning|error|debug|critical)|logging\.(?:info|warning|error|debug|critical))\s*\([^)]*(?:author|handle|content|tweet_text|user_?name|email|password)""",
    re.IGNORECASE,
)


def check_logging(privacy_text: str) -> list[str]:
    """Check for undocumented logging of personal data."""
    issues: list[str] = []
    privacy_lower = privacy_text.lower()

    for pyfile in _python_files():
        if "test" in pyfile.name:
            continue
        content = pyfile.read_text()
        rel = pyfile.relative_to(REPO_ROOT)
        for m in _PERSONAL_DATA_LOG_RE.finditer(content):
            match_text = m.group(0)
            if ("no tweet content" not in privacy_lower or "no.*author" not in privacy_lower) and str(
                rel
            ) not in privacy_lower:
                issues.append(f"Potential personal data logging in {rel}: '{match_text[:80]}...'")

    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    if not PRIVACY_MD.exists():
        print("FAIL: PRIVACY.md not found at repository root")
        return 1

    privacy_text = _read_privacy()

    all_issues: list[tuple[str, list[str]]] = []

    checks = [
        ("External service calls", check_external_calls),
        ("Database tables", check_db_tables),
        ("Credential env vars", check_credentials),
        ("Web API endpoints", check_web_endpoints),
        ("Personal data logging", check_logging),
    ]

    for name, check_fn in checks:
        issues = check_fn(privacy_text)
        all_issues.append((name, issues))

    # Report
    print("=" * 60)
    print("Privacy Policy Consistency Check")
    print("=" * 60)

    total_issues = 0
    for name, issues in all_issues:
        status = "PASS" if not issues else "FAIL"
        print(f"\n[{status}] {name}")
        for issue in issues:
            print(f"  - {issue}")
            total_issues += 1

    print()
    print("=" * 60)
    if total_issues == 0:
        print("Result: ALL CHECKS PASSED")
        return 0

    print(f"Result: {total_issues} issue(s) found")
    return 1


if __name__ == "__main__":
    sys.exit(main())
