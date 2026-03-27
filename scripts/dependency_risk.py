"""Dependency risk scanner for Python (pyproject.toml) and JS (package.json) dependencies.

Checks PyPI and npm registry APIs for staleness, wide version ranges,
and deprecated status. Outputs a color-coded summary table with risk levels.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PYPROJECT_PATH = Path("pyproject.toml")
PACKAGE_JSON_PATH = Path("twag/web/frontend/package.json")

STALENESS_DAYS = 365  # >1 year since last release = stale

# ANSI colors
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
BOLD = "\033[1m"
RESET = "\033[0m"


@dataclass
class DepRisk:
    name: str
    ecosystem: str  # "python" or "npm"
    version_spec: str
    latest_version: str = ""
    last_release: str = ""
    days_since_release: int = -1
    deprecated: bool = False
    wide_range: bool = False
    risks: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def level(self) -> str:
        if self.error:
            return "unknown"
        if self.deprecated or self.days_since_release > STALENESS_DAYS * 2:
            return "high"
        if self.days_since_release > STALENESS_DAYS or self.wide_range:
            return "medium"
        return "low"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_pyproject_deps(path: Path) -> list[tuple[str, str]]:
    """Minimal TOML parser for the dependencies array in pyproject.toml."""
    text = path.read_text()
    deps: list[tuple[str, str]] = []

    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if stripped == "]":
                break
            # Extract quoted dependency string
            m = re.match(r'^\s*"([^"]+)"', stripped)
            if m:
                dep_str = m.group(1)
                # Split name from version spec (e.g. "click>=8.1.0")
                parts = re.split(r"([><=!~^]+.*)", dep_str, maxsplit=1)
                name = parts[0].strip().split("[")[0]  # strip extras like [standard]
                spec = parts[1].strip() if len(parts) > 1 else ""
                deps.append((name, spec))
    return deps


def parse_package_json_deps(path: Path) -> list[tuple[str, str]]:
    """Parse dependencies + devDependencies from package.json."""
    data = json.loads(path.read_text())
    deps: list[tuple[str, str]] = []
    for section in ("dependencies", "devDependencies"):
        for name, version in data.get(section, {}).items():
            deps.append((name, version))
    return deps


# ---------------------------------------------------------------------------
# Version range analysis
# ---------------------------------------------------------------------------


def is_wide_python_range(spec: str) -> bool:
    """Check if a Python version spec has no upper bound (only >= or ~=)."""
    if not spec:
        return True
    # Has an upper bound if it contains < or <=
    if "<" in spec:
        return False
    # ~= (compatible release) and == are bounded
    if spec.startswith(("~=", "==")):
        return False
    return True


def is_wide_npm_range(spec: str) -> bool:
    """Check if an npm version spec has no upper bound (>= only, or *)."""
    spec = spec.strip()
    if spec in ("*", "latest", ""):
        return True
    if spec.startswith(">=") and "<" not in spec:
        return True
    # ^ and ~ are bounded by major/minor, so they're acceptable
    return False


# ---------------------------------------------------------------------------
# Registry queries
# ---------------------------------------------------------------------------


def _fetch_json(url: str) -> dict | None:
    """Fetch JSON from a URL, returning None on error."""
    try:
        req = Request(url, headers={"Accept": "application/json", "User-Agent": "twag-dep-scanner/1.0"})
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError):
        return None


def check_pypi(name: str, spec: str) -> DepRisk:
    risk = DepRisk(name=name, ecosystem="python", version_spec=spec)

    # Normalize: PyPI uses lowercase with hyphens
    pypi_name = name.lower().replace("_", "-")
    data = _fetch_json(f"https://pypi.org/pypi/{pypi_name}/json")

    if data is None:
        risk.error = "PyPI lookup failed"
        return risk

    info = data.get("info", {})
    risk.latest_version = info.get("version", "?")

    # Deprecated check — PyPI marks via classifiers
    classifiers = info.get("classifiers", [])
    if any("Inactive" in c or "Deprecated" in c for c in classifiers):
        risk.deprecated = True
        risk.risks.append("deprecated")

    # Last release date from the latest version's upload
    releases = data.get("releases", {})
    latest_files = releases.get(risk.latest_version, [])
    if latest_files:
        upload_time_str = latest_files[0].get("upload_time_iso_8601") or latest_files[0].get("upload_time", "")
        if upload_time_str:
            # Handle both formats: with and without timezone
            upload_time_str = upload_time_str.replace("Z", "+00:00")
            try:
                upload_dt = datetime.fromisoformat(upload_time_str)
                if upload_dt.tzinfo is None:
                    upload_dt = upload_dt.replace(tzinfo=timezone.utc)
                risk.last_release = upload_dt.strftime("%Y-%m-%d")
                risk.days_since_release = (datetime.now(timezone.utc) - upload_dt).days
                if risk.days_since_release > STALENESS_DAYS:
                    risk.risks.append(f"stale ({risk.days_since_release}d)")
            except ValueError:
                pass

    # Wide range check
    risk.wide_range = is_wide_python_range(spec)
    if risk.wide_range:
        risk.risks.append("wide range (no upper bound)")

    return risk


def check_npm(name: str, spec: str) -> DepRisk:
    risk = DepRisk(name=name, ecosystem="npm", version_spec=spec)

    data = _fetch_json(f"https://registry.npmjs.org/{name}")
    if data is None:
        risk.error = "npm lookup failed"
        return risk

    # Deprecated — npm sets this at the package or version level
    dist_tags = data.get("dist-tags", {})
    latest_tag = dist_tags.get("latest", "")
    risk.latest_version = latest_tag

    # Check if deprecated (package-level or latest version level)
    versions = data.get("versions", {})
    latest_meta = versions.get(latest_tag, {})
    if latest_meta.get("deprecated"):
        risk.deprecated = True
        risk.risks.append("deprecated")

    # Last publish date
    time_info = data.get("time", {})
    modified = time_info.get(latest_tag) or time_info.get("modified", "")
    if modified:
        try:
            mod_dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            if mod_dt.tzinfo is None:
                mod_dt = mod_dt.replace(tzinfo=timezone.utc)
            risk.last_release = mod_dt.strftime("%Y-%m-%d")
            risk.days_since_release = (datetime.now(timezone.utc) - mod_dt).days
            if risk.days_since_release > STALENESS_DAYS:
                risk.risks.append(f"stale ({risk.days_since_release}d)")
        except ValueError:
            pass

    # Wide range check
    risk.wide_range = is_wide_npm_range(spec)
    if risk.wide_range:
        risk.risks.append("wide range (no upper bound)")

    return risk


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def color_for_level(level: str) -> str:
    return {"high": RED, "medium": YELLOW, "low": GREEN, "unknown": YELLOW}.get(level, RESET)


def print_table(results: list[DepRisk]) -> None:
    header = (
        f"{'Ecosystem':<10} {'Package':<35} {'Spec':<18} {'Latest':<12} {'Last Release':<14} {'Risk':<8} {'Details'}"
    )
    print(f"\n{BOLD}Dependency Risk Report{RESET}")
    print("=" * len(header))
    print(f"{BOLD}{header}{RESET}")
    print("-" * len(header))

    for r in sorted(results, key=lambda x: {"high": 0, "medium": 1, "unknown": 2, "low": 3}[x.level]):
        color = color_for_level(r.level)
        details = r.error or (", ".join(r.risks) if r.risks else "ok")
        print(
            f"{r.ecosystem:<10} {r.name:<35} {r.version_spec:<18} {r.latest_version:<12} "
            f"{r.last_release:<14} {color}{r.level:<8}{RESET} {details}"
        )

    print()


def to_json(results: list[DepRisk]) -> str:
    return json.dumps(
        [
            {
                "name": r.name,
                "ecosystem": r.ecosystem,
                "version_spec": r.version_spec,
                "latest_version": r.latest_version,
                "last_release": r.last_release,
                "days_since_release": r.days_since_release,
                "deprecated": r.deprecated,
                "wide_range": r.wide_range,
                "risk_level": r.level,
                "risks": r.risks,
                "error": r.error,
            }
            for r in results
        ],
        indent=2,
    )


def main() -> int:
    results: list[DepRisk] = []

    if PYPROJECT_PATH.exists():
        print(f"Scanning {PYPROJECT_PATH} ...")
        for name, spec in parse_pyproject_deps(PYPROJECT_PATH):
            results.append(check_pypi(name, spec))
    else:
        print(f"Warning: {PYPROJECT_PATH} not found, skipping Python deps")

    if PACKAGE_JSON_PATH.exists():
        print(f"Scanning {PACKAGE_JSON_PATH} ...")
        for name, spec in parse_package_json_deps(PACKAGE_JSON_PATH):
            results.append(check_npm(name, spec))
    else:
        print(f"Warning: {PACKAGE_JSON_PATH} not found, skipping JS deps")

    if not results:
        print("No dependencies found to scan.")
        return 0

    print_table(results)

    # Also emit JSON for machine consumption
    if "--json" in sys.argv:
        print(to_json(results))

    high_count = sum(1 for r in results if r.level == "high")
    medium_count = sum(1 for r in results if r.level == "medium")
    print(f"Summary: {high_count} high, {medium_count} medium, {len(results) - high_count - medium_count} low/unknown")

    # Exit non-zero only if there are high-risk deps
    return 1 if high_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
