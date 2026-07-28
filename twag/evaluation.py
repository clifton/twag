"""Golden-set evaluation for triage prompt changes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .scorer import TriageResult, load_fund_context, triage_tweets_batch

_PACKAGED_GOLDEN_PATH = Path(__file__).parent / "data" / "golden.jsonl"
_SOURCE_GOLDEN_PATH = Path(__file__).parents[1] / "tests" / "eval" / "golden.jsonl"
DEFAULT_GOLDEN_PATH = _PACKAGED_GOLDEN_PATH if _PACKAGED_GOLDEN_PATH.exists() else _SOURCE_GOLDEN_PATH


@dataclass
class GoldenReport:
    """Aggregate accuracy measures for the triage golden set."""

    total: int
    band_accuracy: float
    surprise_accuracy: float
    stale_accuracy: float
    trigger_precision: float
    trigger_recall: float
    catalyst_accuracy: float
    direction_accuracy: float

    @property
    def passed(self) -> bool:
        """Apply deliberately modest v0 gates while the new scale calibrates."""
        return bool(
            self.total >= 20
            and self.band_accuracy >= 0.60
            and self.surprise_accuracy >= 0.60
            and self.stale_accuracy >= 0.75
            and self.trigger_precision >= 0.70
            and self.trigger_recall >= 0.70
            and self.catalyst_accuracy >= 0.70
            and self.direction_accuracy >= 0.60,
        )


def load_golden_fixtures(path: Path = DEFAULT_GOLDEN_PATH) -> list[dict[str, Any]]:
    """Load hand-curated JSONL fixtures without accessing the deployed database."""
    fixtures = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or "expected" not in item:
            raise ValueError(f"invalid golden fixture at line {line_number}")
        fixtures.append(item)
    return fixtures


def score_golden_results(
    fixtures: list[dict[str, Any]],
    results: list[TriageResult],
) -> GoldenReport:
    """Compare scorer output with labeled bands and classifications."""
    expected_by_id = {str(item["id"]): item["expected"] for item in fixtures}
    result_by_id = {result.tweet_id: result for result in results}
    total = len(fixtures)
    if total == 0:
        return GoldenReport(0, 0, 0, 0, 0, 0, 0, 0)

    band_hits = surprise_hits = stale_hits = catalyst_hits = direction_hits = 0
    trigger_tp = trigger_fp = trigger_fn = 0
    for tweet_id, expected in expected_by_id.items():
        result = result_by_id.get(tweet_id)
        if result is None:
            trigger = expected.get("playbook_trigger")
            if trigger and trigger != "vol_substitution":
                trigger_fn += 1
            continue
        if float(expected["score_min"]) <= result.score <= float(expected["score_max"]):
            band_hits += 1
        surprise_hits += result.surprise == expected.get("surprise", 0)
        stale_hits += result.is_stale_repeat is bool(expected.get("is_stale_repeat", False))
        catalyst_hits += result.catalyst_status == expected.get("catalyst")
        direction_hits += result.direction == expected.get("direction", "na")

        expected_trigger = expected.get("playbook_trigger")
        actual_trigger = result.playbook_trigger
        if expected_trigger == "vol_substitution":
            continue
        if actual_trigger == "vol_substitution":
            actual_trigger = None
        if actual_trigger and actual_trigger == expected_trigger:
            trigger_tp += 1
        else:
            if actual_trigger:
                trigger_fp += 1
            if expected_trigger:
                trigger_fn += 1

    precision_denominator = trigger_tp + trigger_fp
    recall_denominator = trigger_tp + trigger_fn
    return GoldenReport(
        total=total,
        band_accuracy=band_hits / total,
        surprise_accuracy=surprise_hits / total,
        stale_accuracy=stale_hits / total,
        trigger_precision=trigger_tp / precision_denominator if precision_denominator else 1.0,
        trigger_recall=trigger_tp / recall_denominator if recall_denominator else 1.0,
        catalyst_accuracy=catalyst_hits / total,
        direction_accuracy=direction_hits / total,
    )


def run_golden_eval(
    *,
    path: Path = DEFAULT_GOLDEN_PATH,
    model: str | None = None,
    provider: str | None = None,
) -> GoldenReport:
    """Score the golden fixtures through the current prompt and return a report."""
    fixtures = load_golden_fixtures(path)
    context, _ = load_fund_context()
    tweets = [
        {
            "id": str(item["id"]),
            "handle": str(item["handle"]),
            "text": str(item["text"]),
            "author_context": str(item.get("author_context") or "unranked"),
        }
        for item in fixtures
    ]
    results = triage_tweets_batch(tweets, model=model, provider=provider, fund_context=context)
    return score_golden_results(fixtures, results)
