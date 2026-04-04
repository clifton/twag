#!/usr/bin/env python3
"""Standalone bus factor analysis script.

Usage:
    python scripts/bus_factor.py [repo_dir]

Outputs JSON report to stdout. Optionally save to a file:
    python scripts/bus_factor.py > tmp/bus_factor_report.json
"""

import sys
from pathlib import Path

# Allow running from repo root without install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from twag.bus_factor import analyze_repo, format_report_json


def main():
    repo_dir = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent)
    report = analyze_repo(repo_dir)
    print(format_report_json(report))


if __name__ == "__main__":
    main()
