#!/usr/bin/env python3
"""Standalone entry-point for the roadmap entropy detector.

Core logic lives in ``twag.entropy``; this script provides a convenient
``python scripts/roadmap_entropy.py`` invocation.
"""

from __future__ import annotations

import argparse
import json

from twag.entropy import (
    build_report,
    detect_drift,
    format_text_report,
    load_roadmap,
    parse_git_log,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Roadmap entropy detector")
    parser.add_argument("--days", type=int, default=30, help="Look-back window in days")
    parser.add_argument("--format", choices=["json", "text"], default="text", dest="fmt")
    parser.add_argument("--roadmap-file", default=".roadmap.yml", help="Path to roadmap YAML")
    parser.add_argument("--repo", default=None, help="Path to git repository")
    args = parser.parse_args(argv)

    roadmap = load_roadmap(args.roadmap_file)
    commits = parse_git_log(days=args.days, repo_path=args.repo)
    signals = detect_drift(commits, roadmap_weights=roadmap)
    report = build_report(commits, signals, roadmap_weights=roadmap, days=args.days)

    if args.fmt == "json":
        print(json.dumps(report, indent=2))
    else:
        print(format_text_report(report))


if __name__ == "__main__":
    main()
