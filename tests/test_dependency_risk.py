"""Tests for the dependency risk scanner."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from scripts.dependency_risk import (
    build_report,
    classify_risks,
    major_drift,
    parse_js_constraint,
    parse_package_json,
    parse_pyproject,
    parse_python_dep,
    version_tuple,
)

# ── Version parsing ──────────────────────────────────────────────────


class TestParsePythonDep:
    def test_basic_gte(self):
        assert parse_python_dep("click>=8.1.0") == ("click", ">=", "8.1.0")

    def test_extras_stripped(self):
        assert parse_python_dep("uvicorn[standard]>=0.27.0") == ("uvicorn", ">=", "0.27.0")

    def test_exact_pin(self):
        assert parse_python_dep("pydantic==2.0") == ("pydantic", "==", "2.0")

    def test_bare_name(self):
        name, op, ver = parse_python_dep("ty")
        assert name == "ty"
        assert op == ""


class TestParseJsConstraint:
    def test_caret(self):
        assert parse_js_constraint("^5.62.0") == ("^", "5.62.0")

    def test_tilde(self):
        assert parse_js_constraint("~2.6.0") == ("~", "2.6.0")

    def test_exact(self):
        assert parse_js_constraint("19.0.0") == ("", "19.0.0")


class TestVersionHelpers:
    def test_version_tuple(self):
        assert version_tuple("1.2.3") == (1, 2, 3)
        assert version_tuple("10.0") == (10, 0)

    def test_major_drift(self):
        assert major_drift("1.0.0", "3.2.1") == 2
        assert major_drift("2.0", "2.5") == 0
        assert major_drift("", "1.0") == 0


# ── Risk classification ──────────────────────────────────────────────


class TestClassifyRisks:
    def test_deprecated(self):
        risks = classify_risks(
            "pkg",
            ecosystem="python",
            operator=">=",
            pinned_version="1.0",
            latest_version="1.1",
            last_release=datetime.now(timezone.utc).isoformat(),
            source_url="https://github.com/x/y",
            deprecated=True,
        )
        assert "deprecated" in risks

    def test_stale(self):
        old_date = (datetime.now(timezone.utc) - timedelta(days=500)).isoformat()
        risks = classify_risks(
            "pkg",
            ecosystem="python",
            operator=">=",
            pinned_version="1.0",
            latest_version="1.1",
            last_release=old_date,
            source_url="https://github.com/x/y",
            deprecated=False,
        )
        assert any("stale" in r for r in risks)

    def test_not_stale(self):
        recent = datetime.now(timezone.utc).isoformat()
        risks = classify_risks(
            "pkg",
            ecosystem="python",
            operator=">=",
            pinned_version="1.0",
            latest_version="1.1",
            last_release=recent,
            source_url="https://github.com/x/y",
            deprecated=False,
        )
        assert not any("stale" in r for r in risks)

    def test_major_drift_flagged(self):
        risks = classify_risks(
            "pkg",
            ecosystem="python",
            operator=">=",
            pinned_version="1.0",
            latest_version="3.5",
            last_release=datetime.now(timezone.utc).isoformat(),
            source_url="https://github.com/x/y",
            deprecated=False,
        )
        assert any("drift" in r for r in risks)

    def test_no_source_repo(self):
        risks = classify_risks(
            "pkg",
            ecosystem="python",
            operator=">=",
            pinned_version="1.0",
            latest_version="1.1",
            last_release=datetime.now(timezone.utc).isoformat(),
            source_url="",
            deprecated=False,
        )
        assert "no source repo" in risks

    def test_permissive_python(self):
        risks = classify_risks(
            "pkg",
            ecosystem="python",
            operator="",
            pinned_version="",
            latest_version="1.0",
            last_release=datetime.now(timezone.utc).isoformat(),
            source_url="https://github.com/x/y",
            deprecated=False,
        )
        assert "permissive constraint" in risks

    def test_permissive_npm(self):
        risks = classify_risks(
            "pkg",
            ecosystem="npm",
            operator="",
            pinned_version="1.0",
            latest_version="1.0",
            last_release=datetime.now(timezone.utc).isoformat(),
            source_url="https://github.com/x/y",
            deprecated=False,
        )
        assert "permissive constraint" in risks

    def test_clean(self):
        risks = classify_risks(
            "pkg",
            ecosystem="python",
            operator=">=",
            pinned_version="1.0",
            latest_version="1.5",
            last_release=datetime.now(timezone.utc).isoformat(),
            source_url="https://github.com/x/y",
            deprecated=False,
        )
        assert risks == []


# ── File parsing ─────────────────────────────────────────────────────


class TestParsePyproject:
    def test_parse(self, tmp_path):
        toml = tmp_path / "pyproject.toml"
        toml.write_text('[project]\ndependencies = [\n  "click>=8.1.0",\n  "httpx>=0.27.0",\n]\n')
        deps = parse_pyproject(toml)
        assert len(deps) == 2
        assert deps[0]["name"] == "click"
        assert deps[0]["operator"] == ">="
        assert deps[0]["version"] == "8.1.0"


class TestParsePackageJson:
    def test_parse(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(
            json.dumps(
                {
                    "dependencies": {"react": "^19.0.0"},
                    "devDependencies": {"vite": "^6.0.0"},
                }
            )
        )
        deps = parse_package_json(pkg)
        assert len(deps) == 2
        react = next(d for d in deps if d["name"] == "react")
        assert react["operator"] == "^"
        assert react["version"] == "19.0.0"
        vite = next(d for d in deps if d["name"] == "vite")
        assert vite["dev"] is True


# ── Report building with mocked API ─────────────────────────────────


class TestBuildReport:
    def test_report_structure(self):
        """Build a report with a mock HTTP client."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        recent = datetime.now(timezone.utc).isoformat()
        mock_resp.json.return_value = {
            "info": {
                "version": "8.2.0",
                "project_urls": {"Repository": "https://github.com/pallets/click"},
                "classifiers": [],
            },
            "releases": {"8.2.0": [{"upload_time_iso_8601": recent}]},
        }
        mock_client.get.return_value = mock_resp

        python_deps = [{"name": "click", "operator": ">=", "version": "8.1.0", "raw": "click>=8.1.0"}]
        report = build_report(python_deps, [], mock_client)

        assert report["total_packages"] == 1
        assert "entries" in report
        assert report["entries"][0]["name"] == "click"
        assert report["entries"][0]["ecosystem"] == "python"

    def test_handles_api_error(self):
        """Report should record error when API returns 404."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client.get.return_value = mock_resp

        python_deps = [{"name": "nonexistent-pkg", "operator": ">=", "version": "1.0", "raw": "nonexistent-pkg>=1.0"}]
        report = build_report(python_deps, [], mock_client)

        assert report["flagged_packages"] == 1
        assert "not found" in report["entries"][0]["risks"][0]
