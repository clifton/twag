#!/usr/bin/env python3
"""Standalone roadmap entropy analysis script.

Usage:
    python scripts/roadmap_entropy.py [--days 90] [--json] [--repo-path /path/to/repo]
"""

from __future__ import annotations

import argparse
import json

from twag.entropy import analyze_entropy


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect roadmap scope creep and drift from git history.")
    parser.add_argument("--days", type=int, default=90, help="Days of history to analyze (default: 90)")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Output JSON instead of text")
    parser.add_argument("--repo-path", default=None, help="Path to git repository (default: current dir)")
    args = parser.parse_args()

    report = analyze_entropy(days=args.days, repo_path=args.repo_path)

    if args.as_json:
        data = {
            "overall_score": round(report.overall_score, 1),
            "commit_topic_entropy": round(report.commit_topic_entropy, 3),
            "file_churn_dispersion": round(report.file_churn_dispersion, 3),
            "surface_area_delta": report.surface_area_delta,
            "todo_accumulation": report.todo_accumulation,
            "doc_staleness_ratio": round(report.doc_staleness_ratio, 3),
            "topic_counts": report.topic_counts,
            "churn_hotspots": [{"file": f, "changes": c} for f, c in report.churn_hotspots],
            "drift_indicators": [
                {"category": d.category, "description": d.description, "severity": d.severity}
                for d in report.drift_indicators
            ],
            "recommendations": report.recommendations,
        }
        print(json.dumps(data, indent=2))
        return

    score = report.overall_score
    if score < 30:
        label = "Low"
    elif score < 60:
        label = "Moderate"
    else:
        label = "High"

    print(f"Roadmap Entropy Report (last {args.days} days)")
    print(f"Overall Score: {score:.0f}/100 ({label} entropy)")
    print()
    print("Metrics:")
    print(f"  Commit topic entropy:  {report.commit_topic_entropy:.3f}")
    print(f"  File churn dispersion: {report.file_churn_dispersion:.3f}")
    print(f"  Surface area delta:    {report.surface_area_delta:+d} files")
    print(f"  TODO/FIXME count:      {report.todo_accumulation}")
    print(f"  Doc staleness:         {report.doc_staleness_ratio:.0%}")
    print()

    if report.topic_counts:
        print("Commit Topics:")
        for topic, count in sorted(report.topic_counts.items(), key=lambda x: -x[1]):
            print(f"  {topic:<12} {count}")
        print()

    if report.churn_hotspots:
        print("Churn Hotspots (top 10):")
        for filepath, count in report.churn_hotspots:
            print(f"  {count:>4}  {filepath}")
        print()

    if report.drift_indicators:
        print("Drift Indicators:")
        for ind in report.drift_indicators:
            print(f"  [{ind.severity.upper()}] {ind.description}")
        print()

    if report.recommendations:
        print("Recommendations:")
        for rec in report.recommendations:
            print(f"  - {rec}")


if __name__ == "__main__":
    main()
