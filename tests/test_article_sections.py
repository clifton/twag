"""Unit tests for shared article section parsing helpers."""

import json

from twag.article_sections import format_confidence, normalize_horizon, parse_action_items, parse_primary_points


def test_parse_primary_points_filters_invalid_entries():
    payload = json.dumps(
        [
            {
                "point": "Google capex is entering a new regime.",
                "reasoning": "Demand backlog supports accelerated deployment.",
                "evidence": "$240B backlog and strong cloud growth.",
            },
            {"point": "", "reasoning": "invalid"},
            {"reasoning": "missing point"},
            "not-a-dict",
        ]
    )

    points = parse_primary_points(payload)

    assert points == [
        {
            "point": "Google capex is entering a new regime.",
            "reasoning": "Demand backlog supports accelerated deployment.",
            "evidence": "$240B backlog and strong cloud growth.",
        }
    ]


def test_parse_action_items_normalizes_horizon_confidence_and_tickers():
    payload = json.dumps(
        [
            {
                "action": "Track quarterly GCP growth and backlog trends.",
                "trigger": "Growth below 30% plus backlog stall.",
                "horizon": "medium_term",
                "confidence": 0.65,
                "tickers": ["GOOGL", " MSFT ", "", "AMZN"],
            },
            {"action": "", "trigger": "invalid"},
            {"trigger": "missing action"},
        ]
    )

    actions = parse_action_items(payload)

    assert actions == [
        {
            "action": "Track quarterly GCP growth and backlog trends.",
            "trigger": "Growth below 30% plus backlog stall.",
            "horizon": "medium term",
            "confidence": "0.65",
            "tickers": "GOOGL, MSFT, AMZN",
        }
    ]


def test_parse_action_items_handles_missing_or_bad_json():
    assert parse_action_items(None) == []
    assert parse_action_items("") == []
    assert parse_action_items("not-json") == []
    assert parse_action_items(json.dumps({"action": "wrong shape"})) == []


def test_normalize_horizon_and_confidence_helpers():
    assert normalize_horizon("near_term") == "near term"
    assert normalize_horizon("  ") == ""
    assert format_confidence(0.7) == "0.7"
    assert format_confidence(0.65) == "0.65"
    assert format_confidence(True) == "true"
    assert format_confidence(" high ") == "high"
    assert format_confidence(None) == ""
