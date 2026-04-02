#!/usr/bin/env python3
"""Privacy policy consistency checker.

Validates that PRIVACY.md accurately reflects the codebase by checking:
- External services and their HTTP libraries
- Database tables documented vs. defined in schema
- Web API endpoints documented vs. defined in route files
- Credential/env var documentation
- Third-party CDN/font usage in frontend HTML
- Absence of personal data in logging statements
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRIVACY_MD = REPO_ROOT / "PRIVACY.md"
SCHEMA_PY = REPO_ROOT / "twag" / "db" / "schema.py"
ROUTES_DIR = REPO_ROOT / "twag" / "web" / "routes"
FRONTEND_INDEX = REPO_ROOT / "twag" / "web" / "frontend" / "index.html"
LINK_UTILS = REPO_ROOT / "twag" / "link_utils.py"
NOTIFIER = REPO_ROOT / "twag" / "notifier.py"
LLM_CLIENT = REPO_ROOT / "twag" / "scorer" / "llm_client.py"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_db_tables() -> list[str]:
    """Verify every CREATE TABLE in schema.py is documented in PRIVACY.md."""
    errors: list[str] = []
    schema = read_text(SCHEMA_PY)
    privacy = read_text(PRIVACY_MD)

    # Tables defined in schema
    defined = set(re.findall(r"CREATE\s+(?:VIRTUAL\s+)?TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)", schema))
    # Tables mentioned in PRIVACY.md (in backticks or as table references)
    documented = set(re.findall(r"`(\w+)`\s+table", privacy))
    # Also catch column-qualified references like `tweets.links_json`
    # Only count as table refs if the prefix matches a known schema table
    for candidate in re.findall(r"`(\w+)\.\w+`", privacy):
        if candidate in defined:
            documented.add(candidate)
    # Also catch table names in backtick-only form within the data table
    documented.update(re.findall(r"`(\w+)(?:`,\s*`\w+)*`\s+tables?", privacy))

    # FTS virtual table and triggers are implementation details, skip them
    defined.discard("tweets_fts")

    undocumented = defined - documented
    if undocumented:
        errors.append(f"DB tables in schema.py but not in PRIVACY.md: {sorted(undocumented)}")

    extra = documented - defined
    if extra:
        errors.append(f"DB tables in PRIVACY.md but not in schema.py: {sorted(extra)}")

    return errors


def check_web_endpoints() -> list[str]:
    """Verify web endpoints in route files match PRIVACY.md documentation."""
    errors: list[str] = []
    privacy = read_text(PRIVACY_MD)

    # Extract documented endpoints from PRIVACY.md
    documented_endpoints: set[str] = set()
    for match in re.finditer(r"- `(GET|POST|PUT|DELETE)\s+(/api/[^`]+)`", privacy):
        method, path = match.groups()
        documented_endpoints.add(f"{method} {path}")

    # Extract endpoints from route files
    code_endpoints: set[str] = set()
    for route_file in ROUTES_DIR.glob("*.py"):
        if route_file.name == "__init__.py":
            continue
        source = read_text(route_file)
        # Match FastAPI decorator patterns like @router.get("/tweets")
        for match in re.finditer(r"@router\.(get|post|put|delete)\(\s*\"([^\"]+)\"", source):
            method, path = match.groups()
            code_endpoints.add(f"{method.upper()} /api{path}")

    missing_from_docs = code_endpoints - documented_endpoints
    if missing_from_docs:
        errors.append(f"Endpoints in code but not in PRIVACY.md: {sorted(missing_from_docs)}")

    extra_in_docs = documented_endpoints - code_endpoints
    if extra_in_docs:
        errors.append(f"Endpoints in PRIVACY.md but not in code: {sorted(extra_in_docs)}")

    return errors


def check_external_services() -> list[str]:
    """Verify external service claims in PRIVACY.md match the code."""
    errors: list[str] = []
    privacy = read_text(PRIVACY_MD)

    # Check urllib.request usage for t.co expansion
    if LINK_UTILS.exists():
        link_src = read_text(LINK_UTILS)
        if ("urlopen" in link_src or "urllib.request" in link_src) and "urllib.request" not in privacy:
            errors.append("link_utils.py uses urllib.request but PRIVACY.md doesn't document it")
        if "t.co" in link_src and "t.co" not in privacy:
            errors.append("link_utils.py references t.co but PRIVACY.md doesn't document it")

    # Check httpx usage for Telegram
    if NOTIFIER.exists():
        notifier_src = read_text(NOTIFIER)
        if "httpx" in notifier_src and "Telegram" not in privacy:
            errors.append("notifier.py uses httpx for Telegram but PRIVACY.md doesn't document Telegram")

    # Check LLM client libraries
    if LLM_CLIENT.exists():
        llm_src = read_text(LLM_CLIENT)
        if ("google" in llm_src or "genai" in llm_src) and "Gemini" not in privacy:
            errors.append("llm_client.py uses Google Gemini but PRIVACY.md doesn't document it")
        if "anthropic" in llm_src and "Anthropic" not in privacy and "Claude" not in privacy:
            errors.append("llm_client.py uses Anthropic but PRIVACY.md doesn't document it")

    return errors


def check_google_fonts() -> list[str]:
    """Verify Google Fonts CDN usage is documented if present in frontend."""
    errors: list[str] = []
    privacy = read_text(PRIVACY_MD)

    # Check all HTML files that might load fonts
    html_files = list((REPO_ROOT / "twag" / "web" / "frontend").rglob("*.html"))
    for html_file in html_files:
        html_src = read_text(html_file)
        if "fonts.googleapis.com" in html_src or "fonts.gstatic.com" in html_src:
            if "Google Fonts" not in privacy and "fonts.googleapis.com" not in privacy:
                errors.append(
                    f"{html_file.relative_to(REPO_ROOT)} loads Google Fonts but PRIVACY.md doesn't document it"
                )
            break  # Only need to flag once

    # Reverse check: if PRIVACY.md documents Google Fonts, verify it's actually used
    if "Google Fonts" in privacy:
        found = False
        for html_file in html_files:
            if "fonts.googleapis.com" in read_text(html_file):
                found = True
                break
        if not found:
            errors.append("PRIVACY.md documents Google Fonts but no HTML file loads them")

    return errors


def check_credentials() -> list[str]:
    """Verify credential documentation matches env var usage in code."""
    errors: list[str] = []
    privacy = read_text(PRIVACY_MD)

    # Known credential env vars and the files that use them
    expected_creds = {
        "AUTH_TOKEN": ["twag/auth.py", "twag/cli/init_cmd.py"],
        "CT0": ["twag/auth.py", "twag/cli/init_cmd.py"],
        "GEMINI_API_KEY": ["twag/scorer/llm_client.py", "twag/cli/init_cmd.py"],
        "ANTHROPIC_API_KEY": ["twag/scorer/llm_client.py", "twag/cli/init_cmd.py"],
        "TELEGRAM_BOT_TOKEN": ["twag/notifier.py", "twag/cli/init_cmd.py"],
        "TELEGRAM_CHAT_ID": ["twag/notifier.py", "twag/cli/init_cmd.py"],
    }

    for cred, source_files in expected_creds.items():
        # Check at least one source file references it
        found_in_code = False
        for sf in source_files:
            sf_path = REPO_ROOT / sf
            if sf_path.exists() and cred in read_text(sf_path):
                found_in_code = True
                break

        if found_in_code and cred not in privacy:
            errors.append(f"Credential {cred} used in code but not documented in PRIVACY.md")
        elif not found_in_code and cred in privacy:
            errors.append(f"Credential {cred} documented in PRIVACY.md but not found in code")

    return errors


def check_logging() -> list[str]:
    """Warn if logging statements appear to log personal data."""
    warnings: list[str] = []

    # Patterns that suggest personal data in log statements
    personal_patterns = [
        (r"log.*\b(author_handle|author_name|display_name)\b", "author identity"),
        (r"log.*\bcontent\b.*tweet", "tweet content"),
        (r"log.*\b(AUTH_TOKEN|CT0|API_KEY|BOT_TOKEN)\b", "credentials"),
    ]

    for py_file in (REPO_ROOT / "twag").rglob("*.py"):
        source = read_text(py_file)
        for line_no, line in enumerate(source.splitlines(), 1):
            # Only check lines that look like logging calls
            if not re.search(r"(?:logger?\.|logging\.)\w+\(", line):
                continue
            for pattern, data_type in personal_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    rel = py_file.relative_to(REPO_ROOT)
                    warnings.append(f"{rel}:{line_no} may log {data_type}: {line.strip()[:80]}")

    return warnings


def main() -> int:
    if not PRIVACY_MD.exists():
        print(f"{FAIL}  PRIVACY.md not found at {PRIVACY_MD}")
        return 1

    checks = [
        ("Database tables", check_db_tables),
        ("Web endpoints", check_web_endpoints),
        ("External services", check_external_services),
        ("Google Fonts CDN", check_google_fonts),
        ("Credentials", check_credentials),
        ("Logging (personal data)", check_logging),
    ]

    all_errors: list[str] = []
    all_warnings: list[str] = []

    for name, check_fn in checks:
        results = check_fn()
        if name == "Logging (personal data)":
            # Logging check produces warnings, not hard errors
            if results:
                print(f"  {WARN}  {name}")
                for w in results:
                    print(f"         {w}")
                all_warnings.extend(results)
            else:
                print(f"  {PASS}  {name}")
        elif results:
            print(f"  {FAIL}  {name}")
            for e in results:
                print(f"         {e}")
            all_errors.extend(results)
        else:
            print(f"  {PASS}  {name}")

    print()
    if all_errors:
        print(f"Privacy check failed with {len(all_errors)} error(s).")
        return 1
    if all_warnings:
        print(f"Privacy check passed with {len(all_warnings)} warning(s).")
        return 0
    print("Privacy check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
