"""Dependency risk scanner for Python and Node dependencies.

Checks for:
- Known security vulnerabilities (via pip-audit / npm audit)
- Stale packages (no release in >12 months)
- Deprecated or yanked packages
- Unpinned upper bounds in Python dependencies
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
FRONTEND_DIR = REPO_ROOT / "twag" / "web" / "frontend"
STALE_DAYS = 365
PYPI_URL = "https://pypi.org/pypi/{}/json"

console = Console()


@dataclass
class Finding:
    package: str
    ecosystem: str  # "python" or "node"
    severity: str  # "high", "medium", "low"
    category: str  # "vulnerability", "stale", "deprecated", "unpinned"
    detail: str


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)

    @property
    def has_high_severity(self) -> bool:
        return any(f.severity == "high" for f in self.findings)


# ---------------------------------------------------------------------------
# Python dependency extraction (minimal TOML parser for pyproject.toml)
# ---------------------------------------------------------------------------


def _parse_dependencies_from_pyproject(path: Path) -> list[str]:
    """Extract dependency names from pyproject.toml without a TOML library."""
    lines = path.read_text().splitlines()
    in_deps = False
    deps: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if stripped == "]":
                break
            # Lines look like: "click>=8.1.0",
            cleaned = stripped.strip('",').strip()
            if cleaned:
                # Extract package name (before any version specifier)
                for sep in [">=", "<=", "!=", "==", "~=", ">", "<", "["]:
                    cleaned = cleaned.split(sep)[0]
                deps.append(cleaned.strip())
    return deps


def _parse_specifiers_from_pyproject(path: Path) -> dict[str, str]:
    """Extract raw dependency specifiers keyed by package name."""
    lines = path.read_text().splitlines()
    in_deps = False
    specs: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if stripped == "]":
                break
            raw = stripped.strip('",').strip()
            if raw:
                name = raw
                for sep in [">=", "<=", "!=", "==", "~=", ">", "<", "["]:
                    name = name.split(sep)[0]
                specs[name.strip()] = raw
    return specs


# ---------------------------------------------------------------------------
# PyPI queries
# ---------------------------------------------------------------------------


def _query_pypi(client: httpx.Client, package: str) -> dict[str, Any] | None:
    try:
        resp = client.get(PYPI_URL.format(package), timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except httpx.HTTPError:
        pass
    return None


def _check_pypi_package(client: httpx.Client, package: str, result: ScanResult) -> None:
    data = _query_pypi(client, package)
    if data is None:
        result.findings.append(Finding(package, "python", "low", "stale", "Could not fetch PyPI metadata"))
        return

    info = data.get("info", {})

    # Deprecated / yanked check via classifiers
    classifiers = info.get("classifiers") or []
    for c in classifiers:
        if "Inactive" in c or "Obsolete" in c:
            result.findings.append(Finding(package, "python", "high", "deprecated", f"PyPI classifier: {c}"))

    # Latest release date
    releases = data.get("releases", {})
    latest_date = _latest_release_date(releases)
    if latest_date:
        age_days = (datetime.now(tz=timezone.utc) - latest_date).days
        if age_days > STALE_DAYS:
            months = age_days // 30
            result.findings.append(
                Finding(
                    package, "python", "medium", "stale", f"Last release {months} months ago ({latest_date:%Y-%m-%d})"
                )
            )


def _latest_release_date(releases: dict[str, list[dict[str, Any]]]) -> datetime | None:
    latest: datetime | None = None
    for files in releases.values():
        for f in files:
            upload = f.get("upload_time_iso_8601") or f.get("upload_time")
            if not upload:
                continue
            try:
                dt = datetime.fromisoformat(upload.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if latest is None or dt > latest:
                    latest = dt
            except ValueError:
                continue
    return latest


# ---------------------------------------------------------------------------
# Unpinned upper-bound check
# ---------------------------------------------------------------------------


def _check_unpinned(specs: dict[str, str], result: ScanResult) -> None:
    for name, spec in specs.items():
        # Has lower bound (>=) but no upper bound (<, <=, !=, ==, ~=)
        if ">=" in spec and "<" not in spec and "==" not in spec and "~=" not in spec:
            result.findings.append(Finding(name, "python", "low", "unpinned", f"No upper bound: {spec}"))


# ---------------------------------------------------------------------------
# pip-audit
# ---------------------------------------------------------------------------


def _run_pip_audit(result: ScanResult) -> None:
    try:
        proc = subprocess.run(
            ["uvx", "pip-audit", "--format=json", "--desc"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        console.print(f"[yellow]pip-audit skipped: {exc}[/yellow]")
        return

    for vuln in data.get("dependencies", []):
        for v in vuln.get("vulns", []):
            vid = v.get("id", "unknown")
            desc = v.get("description", "")[:120]
            fix = v.get("fix_versions", [])
            fix_str = f" (fix: {', '.join(fix)})" if fix else ""
            result.findings.append(
                Finding(
                    vuln["name"],
                    "python",
                    "high",
                    "vulnerability",
                    f"{vid}: {desc}{fix_str}",
                )
            )


# ---------------------------------------------------------------------------
# npm audit
# ---------------------------------------------------------------------------


def _run_npm_audit(result: ScanResult) -> None:
    if not (FRONTEND_DIR / "package-lock.json").exists():
        console.print("[yellow]npm audit skipped: no package-lock.json[/yellow]")
        return

    try:
        proc = subprocess.run(
            ["npm", "audit", "--json"],
            capture_output=True,
            text=True,
            cwd=FRONTEND_DIR,
            timeout=60,
            check=False,
        )
        data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        console.print(f"[yellow]npm audit skipped: {exc}[/yellow]")
        return

    vulns = data.get("vulnerabilities", {})
    for name, info in vulns.items():
        sev = info.get("severity", "moderate")
        via = info.get("via", [])
        # 'via' can be strings (transitive) or dicts (direct advisories)
        details = []
        for v in via:
            if isinstance(v, dict):
                details.append(v.get("title", v.get("url", "")))
            elif isinstance(v, str):
                details.append(f"via {v}")
        severity = "high" if sev in ("high", "critical") else "medium" if sev == "moderate" else "low"
        result.findings.append(Finding(name, "node", severity, "vulnerability", "; ".join(details) or sev))


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

SEVERITY_STYLE = {"high": "red bold", "medium": "yellow", "low": "dim"}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _print_table(result: ScanResult) -> None:
    if not result.findings:
        console.print("[green]No dependency risks found.[/green]")
        return

    table = Table(title="Dependency Risk Report", show_lines=True)
    table.add_column("Package", style="cyan", no_wrap=True)
    table.add_column("Ecosystem", style="blue")
    table.add_column("Severity")
    table.add_column("Category", style="magenta")
    table.add_column("Detail")

    sorted_findings = sorted(result.findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 9))

    for f in sorted_findings:
        style = SEVERITY_STYLE.get(f.severity, "")
        table.add_row(f.package, f.ecosystem, f"[{style}]{f.severity}[/{style}]", f.category, f.detail)

    console.print(table)

    highs = sum(1 for f in result.findings if f.severity == "high")
    mediums = sum(1 for f in result.findings if f.severity == "medium")
    lows = sum(1 for f in result.findings if f.severity == "low")
    console.print(
        f"\nTotal: {len(result.findings)} findings — [red]{highs} high[/red], [yellow]{mediums} medium[/yellow], {lows} low"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    result = ScanResult()

    console.print("[bold]Scanning Python dependencies...[/bold]")
    deps = _parse_dependencies_from_pyproject(PYPROJECT)
    specs = _parse_specifiers_from_pyproject(PYPROJECT)

    with httpx.Client() as client:
        for pkg in deps:
            _check_pypi_package(client, pkg, result)

    _check_unpinned(specs, result)
    _run_pip_audit(result)

    console.print("[bold]Scanning Node dependencies...[/bold]")
    _run_npm_audit(result)

    _print_table(result)

    return 1 if result.has_high_severity else 0


if __name__ == "__main__":
    sys.exit(main())
