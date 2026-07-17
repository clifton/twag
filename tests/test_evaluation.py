"""Golden evaluation harness tests."""

from twag.evaluation import load_golden_fixtures, score_golden_results
from twag.scorer import TriageResult


def test_golden_fixture_is_versioned_non_db_corpus():
    fixtures = load_golden_fixtures()
    assert len(fixtures) == 20
    assert all(item["source"].startswith("hand-transcribed") for item in fixtures)
    assert any(item["expected"]["playbook_trigger"] == "vol_substitution" for item in fixtures)


def test_vol_substitution_canary_is_excluded_from_trigger_coverage():
    fixtures = [
        {
            "id": "canary",
            "expected": {
                "score_min": 8,
                "score_max": 10,
                "surprise": 1,
                "is_stale_repeat": False,
                "playbook_trigger": "vol_substitution",
                "catalyst": None,
                "direction": "short",
            },
        },
    ]
    report = score_golden_results(
        fixtures,
        [TriageResult("canary", 9, [], "", surprise=1, direction="short")],
    )
    assert report.trigger_precision == 1.0
    assert report.trigger_recall == 1.0
