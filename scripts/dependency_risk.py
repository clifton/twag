#!/usr/bin/env python3
"""Dependency risk scanner for Python and JS packages.

Queries PyPI and npm registries to flag:
- Stale packages (no release in >12 months)
- Large version drift (pinned minimum vs latest)
- Deprecated packages
- Missing source repository URLs
- Overly permissive version constraints
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

import httpx
from rich.console import Console
from rich.table import Table

STALE_THRESHOLD_DAYS = 365
PYPI_API = "https://pypi.org/pypi/{}/json"
NPM_API = "https://registry.npmjs.org/{}"
ROOT = Path(__file__).resolve().parent.parent


# ── Version helpers ──────────────────────────────────────────────────


def parse_python_dep(dep: str) -> tuple[str, str, str]:
    """Return (name, operator, version) from a PEP 508 dependency string.

    Strips extras like ``uvicorn[standard]``.
    """
    # Remove extras
    dep = re.sub(r"\[.*?\]", "", dep)
    m = re.match(r"([A-Za-z0-9_.-]+)\s*(>=|==|~=|<=|!=|>|<)?\s*([\d.]*)", dep)
    if not m:
        return dep.strip(), "", ""
    return m.group(1).strip(), (m.group(2) or ""), (m.group(3) or "")


def parse_js_constraint(constraint: str) -> tuple[str, str]:
    """Return (operator, version) from an npm version constraint."""
    m = re.match(r"(\^|~|>=|=|>|<|<=)?\s*([\d.]+)", constraint)
    if not m:
        return "", constraint
    return (m.group(1) or ""), m.group(2)


def version_tuple(v: str) -> tuple[int, ...]:
    """Convert dotted version string to comparable tuple."""
    parts: list[int] = []
    for p in v.split("."):
        digits = re.match(r"\d+", p)
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


def major_drift(pinned: str, latest: str) -> int:
    """Return the major-version difference between *pinned* and *latest*."""
    if not pinned or not latest:
        return 0
    p, la = version_tuple(pinned), version_tuple(latest)
    return max(0, (la[0] if la else 0) - (p[0] if p else 0))


# ── Registry queries ─────────────────────────────────────────────────


def query_pypi(client: httpx.Client, name: str) -> dict:
    """Fetch package metadata from PyPI."""
    try:
        resp = client.get(PYPI_API.format(name), timeout=15)
        if resp.status_code == 404:
            return {"error": "not found on PyPI"}
        resp.raise_for_status()
        data = resp.json()
        info = data.get("info", {})
        urls = info.get("project_urls") or {}
        # Find last release date from releases
        last_release: str | None = None
        for files in reversed(list(data.get("releases", {}).values())):
            for f in files:
                if f.get("upload_time_iso_8601"):
                    last_release = f["upload_time_iso_8601"]
                    break
            if last_release:
                break
        return {
            "latest_version": info.get("version", ""),
            "last_release": last_release,
            "source_url": urls.get("Source") or urls.get("Repository") or urls.get("Homepage") or "",
            "deprecated": "classifiers" in info and any("Inactive" in c for c in (info.get("classifiers") or [])),
        }
    except httpx.HTTPError:
        return {"error": "failed to query PyPI"}


def query_npm(client: httpx.Client, name: str) -> dict:
    """Fetch package metadata from npm registry."""
    try:
        resp = client.get(NPM_API.format(name), timeout=15)
        if resp.status_code == 404:
            return {"error": "not found on npm"}
        resp.raise_for_status()
        data = resp.json()
        latest = (data.get("dist-tags") or {}).get("latest", "")
        time_map = data.get("time") or {}
        last_release = time_map.get(latest) or time_map.get("modified")
        repo = data.get("repository") or {}
        repo_url = repo.get("url", "") if isinstance(repo, dict) else str(repo)
        deprecated = False
        versions = data.get("versions") or {}
        if latest and latest in versions:
            deprecated = bool(versions[latest].get("deprecated"))
        return {
            "latest_version": latest,
            "last_release": last_release,
            "source_url": repo_url,
            "deprecated": deprecated,
        }
    except httpx.HTTPError:
        return {"error": "failed to query npm"}


# ── Risk analysis ────────────────────────────────────────────────────


def classify_risks(
    name: str,
    *,
    ecosystem: str,
    operator: str,
    pinned_version: str,
    latest_version: str,
    last_release: str | None,
    source_url: str,
    deprecated: bool,
) -> list[str]:
    """Return list of risk labels for a package."""
    risks: list[str] = []

    if deprecated:
        risks.append("deprecated")

    # Stale check
    if last_release:
        try:
            release_dt = datetime.fromisoformat(last_release.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - release_dt).days
            if age_days > STALE_THRESHOLD_DAYS:
                risks.append(f"stale ({age_days}d since last release)")
        except (ValueError, TypeError):
            pass

    # Version drift
    drift = major_drift(pinned_version, latest_version)
    if drift >= 2:
        risks.append(f"major drift ({pinned_version} → {latest_version})")

    # Missing source
    if not source_url:
        risks.append("no source repo")

    # Permissive constraint
    if ecosystem == "python" and operator in ("", ">"):
        risks.append("permissive constraint")
    if ecosystem == "npm" and operator == "":
        risks.append("permissive constraint")

    return risks


# ── Parsing ──────────────────────────────────────────────────────────


def parse_pyproject(path: Path) -> list[dict]:
    """Parse Python dependencies from pyproject.toml."""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    deps = data.get("project", {}).get("dependencies", [])
    results = []
    for dep in deps:
        name, op, ver = parse_python_dep(dep)
        results.append({"name": name, "operator": op, "version": ver, "raw": dep})
    return results


def parse_package_json(path: Path) -> list[dict]:
    """Parse JS dependencies from package.json."""
    with open(path) as f:
        data = json.load(f)
    results = []
    for section in ("dependencies", "devDependencies"):
        for name, constraint in (data.get(section) or {}).items():
            op, ver = parse_js_constraint(constraint)
            results.append(
                {"name": name, "operator": op, "version": ver, "raw": constraint, "dev": section == "devDependencies"}
            )
    return results


# ── Report generation ────────────────────────────────────────────────


def build_report(
    python_deps: list[dict],
    js_deps: list[dict],
    client: httpx.Client,
) -> dict:
    """Build full risk report by querying registries."""
    entries: list[dict] = []

    for dep in python_deps:
        info = query_pypi(client, dep["name"])
        if "error" in info:
            entries.append(
                {
                    "name": dep["name"],
                    "ecosystem": "python",
                    "pinned": dep["version"],
                    "latest": "",
                    "risks": [info["error"]],
                }
            )
            continue
        risks = classify_risks(
            dep["name"],
            ecosystem="python",
            operator=dep["operator"],
            pinned_version=dep["version"],
            latest_version=info.get("latest_version", ""),
            last_release=info.get("last_release"),
            source_url=info.get("source_url", ""),
            deprecated=info.get("deprecated", False),
        )
        entries.append(
            {
                "name": dep["name"],
                "ecosystem": "python",
                "pinned": dep["version"],
                "latest": info.get("latest_version", ""),
                "risks": risks,
            }
        )

    for dep in js_deps:
        info = query_npm(client, dep["name"])
        if "error" in info:
            entries.append(
                {
                    "name": dep["name"],
                    "ecosystem": "npm",
                    "pinned": dep["version"],
                    "latest": "",
                    "risks": [info["error"]],
                }
            )
            continue
        risks = classify_risks(
            dep["name"],
            ecosystem="npm",
            operator=dep["operator"],
            pinned_version=dep["version"],
            latest_version=info.get("latest_version", ""),
            last_release=info.get("last_release"),
            source_url=info.get("source_url", ""),
            deprecated=info.get("deprecated", False),
        )
        entries.append(
            {
                "name": dep["name"],
                "ecosystem": "npm",
                "pinned": dep["version"],
                "latest": info.get("latest_version", ""),
                "risks": risks,
                "dev": dep.get("dev", False),
            }
        )

    flagged = [e for e in entries if e["risks"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_packages": len(entries),
        "flagged_packages": len(flagged),
        "entries": entries,
    }


def print_summary(report: dict, console: Console | None = None) -> None:
    """Print a Rich table summarising flagged packages."""
    console = console or Console()
    entries = report.get("entries", [])
    flagged = [e for e in entries if e["risks"]]

    if not flagged:
        console.print("[green]No dependency risks detected.[/green]")
        return

    table = Table(title="Dependency Risk Report", show_lines=True)
    table.add_column("Package", style="bold")
    table.add_column("Ecosystem")
    table.add_column("Pinned")
    table.add_column("Latest")
    table.add_column("Risks", style="red")

    for e in flagged:
        table.add_row(
            e["name"],
            e["ecosystem"],
            e.get("pinned", ""),
            e.get("latest", ""),
            "\n".join(e["risks"]),
        )

    console.print(table)
    console.print(f"\n[bold]{report['flagged_packages']}/{report['total_packages']}[/bold] packages flagged")


# ── Main ─────────────────────────────────────────────────────────────


def main(root: Path | None = None, output_json: Path | None = None) -> dict:
    """Run the scanner and return the report."""
    root = root or ROOT
    pyproject = root / "pyproject.toml"
    package_json = root / "twag" / "web" / "frontend" / "package.json"

    python_deps = parse_pyproject(pyproject) if pyproject.exists() else []
    js_deps = parse_package_json(package_json) if package_json.exists() else []

    with httpx.Client() as client:
        report = build_report(python_deps, js_deps, client)

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2))

    print_summary(report)
    return report


if __name__ == "__main__":
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    report = main(output_json=output)
    sys.exit(1 if report["flagged_packages"] > 0 else 0)
