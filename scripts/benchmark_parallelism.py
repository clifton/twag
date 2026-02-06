#!/usr/bin/env python3
"""Deterministic timing harness for tweet processing parallelization."""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import twag.processor as processor_mod
from twag.db import get_connection, init_db, insert_tweet
from twag.scorer import TriageResult


def _seed_db(db_path: Path, tweet_count: int) -> None:
    init_db(db_path)
    with get_connection(db_path) as conn:
        for idx in range(tweet_count):
            inserted = insert_tweet(
                conn,
                tweet_id=f"bench-{idx:04d}",
                author_handle=f"acct{idx:04d}",
                content=f"Benchmark content {idx} " + ("x" * 700),
                created_at=datetime.now(timezone.utc),
                source="benchmark",
            )
            if not inserted:
                raise RuntimeError(f"Failed to seed tweet bench-{idx:04d}")
        conn.commit()


def _run_triage_case(
    db_path: Path,
    *,
    batch_size: int,
    triage_workers: int,
    text_workers: int,
    triage_latency_s: float,
    summary_latency_s: float,
) -> float:
    original_load_config = processor_mod.load_config
    original_triage_batch = processor_mod.triage_tweets_batch
    original_summarize_tweet = processor_mod.summarize_tweet

    def _fake_load_config() -> dict:
        return {
            "llm": {
                "max_concurrency_text": text_workers,
                "max_concurrency_triage": triage_workers,
                "max_concurrency_vision": 1,
                "vision_model": None,
                "vision_provider": None,
            },
            "scoring": {
                "min_score_for_analysis": 99,
                "min_score_for_article_processing": 99,
            },
        }

    def _fake_triage_tweets_batch(batch, model=None, provider=None):
        time.sleep(triage_latency_s)
        return [
            TriageResult(
                tweet_id=item["id"],
                score=6.0,
                categories=["news"],
                summary="benchmark",
            )
            for item in batch
        ]

    def _fake_summarize_tweet(tweet_text, handle, model=None, provider=None):
        time.sleep(summary_latency_s)
        return f"summary for @{handle}"

    processor_mod.load_config = _fake_load_config
    processor_mod.triage_tweets_batch = _fake_triage_tweets_batch
    processor_mod.summarize_tweet = _fake_summarize_tweet

    try:
        with get_connection(db_path) as conn:
            rows = conn.execute("SELECT * FROM tweets ORDER BY id ASC").fetchall()
            start = time.perf_counter()
            results = processor_mod._triage_rows(
                conn,
                tweet_rows=rows,
                batch_size=batch_size,
                triage_model=None,
                enrich_model=None,
                high_threshold=7.0,
                tier1_handles=set(),
                update_stats=False,
                allow_summarize=True,
                media_min_score=None,
            )
            elapsed = time.perf_counter() - start
            if len(results) != len(rows):
                raise RuntimeError(f"Expected {len(rows)} triage results, got {len(results)}")
            return elapsed
    finally:
        processor_mod.load_config = original_load_config
        processor_mod.triage_tweets_batch = original_triage_batch
        processor_mod.summarize_tweet = original_summarize_tweet


def _measure(
    *,
    tweet_count: int,
    batch_size: int,
    low_triage_workers: int,
    high_triage_workers: int,
    text_workers: int,
    triage_latency_s: float,
    summary_latency_s: float,
) -> tuple[float, float]:
    with TemporaryDirectory(prefix="twag-bench-") as tmp_dir:
        base_db = Path(tmp_dir) / "base.db"
        fast_db = Path(tmp_dir) / "fast.db"
        _seed_db(base_db, tweet_count)
        _seed_db(fast_db, tweet_count)

        baseline = _run_triage_case(
            base_db,
            batch_size=batch_size,
            triage_workers=low_triage_workers,
            text_workers=text_workers,
            triage_latency_s=triage_latency_s,
            summary_latency_s=summary_latency_s,
        )
        optimized = _run_triage_case(
            fast_db,
            batch_size=batch_size,
            triage_workers=high_triage_workers,
            text_workers=text_workers,
            triage_latency_s=triage_latency_s,
            summary_latency_s=summary_latency_s,
        )
        return baseline, optimized


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark twag processing parallelization.")
    parser.add_argument("--tweet-count", type=int, default=32, help="Number of synthetic tweets to process.")
    parser.add_argument("--batch-size", type=int, default=4, help="Batch size for triage.")
    parser.add_argument("--text-workers", type=int, default=2, help="Text worker count for both runs.")
    parser.add_argument("--low-triage-workers", type=int, default=1, help="Triage workers in baseline case.")
    parser.add_argument("--high-triage-workers", type=int, default=4, help="Triage workers in optimized case.")
    parser.add_argument("--triage-latency-ms", type=float, default=60.0, help="Mock triage latency per batch.")
    parser.add_argument("--summary-latency-ms", type=float, default=5.0, help="Mock summary latency per tweet.")
    parser.add_argument("--min-speedup", type=float, default=1.35, help="Minimum required baseline/optimized ratio.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    triage_latency_s = args.triage_latency_ms / 1000.0
    summary_latency_s = args.summary_latency_ms / 1000.0

    if args.low_triage_workers >= args.high_triage_workers:
        raise SystemExit("--high-triage-workers must be greater than --low-triage-workers")

    baseline_s, optimized_s = _measure(
        tweet_count=args.tweet_count,
        batch_size=args.batch_size,
        low_triage_workers=args.low_triage_workers,
        high_triage_workers=args.high_triage_workers,
        text_workers=args.text_workers,
        triage_latency_s=triage_latency_s,
        summary_latency_s=summary_latency_s,
    )
    speedup = baseline_s / optimized_s if optimized_s > 0 else 0.0

    print(
        "benchmark_parallelism:"
        f" tweets={args.tweet_count}"
        f" batch_size={args.batch_size}"
        f" baseline_s={baseline_s:.4f}"
        f" optimized_s={optimized_s:.4f}"
        f" speedup={speedup:.3f}x"
        f" min_required={args.min_speedup:.3f}x"
    )

    if speedup < args.min_speedup:
        print("FAIL: measured speedup is below threshold")
        return 1

    print("PASS: measured speedup meets threshold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
