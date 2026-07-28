"""Alert trigger, routing, and registry-match regressions."""

import json

import pytest

from twag.notifier import format_alert, notify_high_signal_tweet, should_alert
from twag.registry import match_positions


@pytest.mark.parametrize(
    ("score", "surprise", "playbook", "catalyst", "expected"),
    [
        (8, 0, None, None, True),
        (7, 2, None, None, True),
        (6, 0, "supply_shock", None, True),
        (6, 0, None, "resolved", True),
        (6, 2, None, None, False),
        (5, 0, "dat_mnav", None, False),
        (5, 0, None, "resolved", False),
    ],
)
def test_should_alert_truth_table(score, surprise, playbook, catalyst, expected):
    assert should_alert(score, surprise, playbook, catalyst, alert_threshold=8) is expected


def _write_registry(root):
    (root / "themes.json").write_text(
        json.dumps(
            {
                "themes": [
                    {"id": "ai-compute", "status": "active"},
                    {"id": "copper-shock", "status": "active"},
                ],
            },
        ),
    )
    (root / "instruments.json").write_text(
        json.dumps(
            {
                "instruments": [
                    {"ticker": "GOOG", "relationship": "owned", "themes": ["ai-compute"]},
                    {"ticker": "FCX", "relationship": "watchlist", "themes": ["copper-shock"]},
                ],
            },
        ),
    )


def test_match_positions_prefers_exact_ticker(tmp_path):
    _write_registry(tmp_path)
    assert match_positions(["ai-compute"], ["FCX"], registry_dir=tmp_path) == "FCX (watchlist)"


def test_match_positions_uses_shared_theme_but_never_cross_theme(tmp_path):
    _write_registry(tmp_path)
    assert match_positions(["ai-compute"], [], registry_dir=tmp_path) == "GOOG (owned, ai-compute)"
    assert match_positions(["copper-shock"], ["UNKNOWN"], registry_dir=tmp_path) == "FCX (watchlist, copper-shock)"
    assert match_positions(["unrelated"], [], registry_dir=tmp_path) is None


def test_match_positions_omits_when_registry_absent(tmp_path):
    assert match_positions(["ai-compute"], ["GOOG"], registry_dir=tmp_path) is None


def test_format_alert_resolution_and_playbook_headers(monkeypatch):
    monkeypatch.setattr("twag.notifier.match_positions", lambda themes, tickers: "MSTR (watchlist, dat-mnav)")
    resolved = format_alert(
        "1",
        "source",
        "Framework resolves stress",
        ["crypto"],
        "Catalyst dead",
        ["MSTR"],
        catalyst_status="resolved",
        themes=["dat-mnav"],
    )
    assert resolved.startswith("⚠️ RESOLVED [CRYPTO]")
    assert "🎯 MSTR (watchlist, dat-mnav)" in resolved

    playbook = format_alert(
        "2",
        "source",
        "Supply offline",
        ["commodities"],
        "590kt offline",
        playbook_trigger="supply_shock",
    )
    assert playbook.startswith("🚨 PLAYBOOK: SUPPLY_SHOCK [COMMODITIES]")


def test_notify_uses_bounded_ron_then_direct_fallback(monkeypatch):
    direct = []
    monkeypatch.setattr(
        "twag.notifier.load_config",
        lambda: {
            "scoring": {"alert_threshold": 8},
            "notifications": {"telegram_enabled": True, "telegram_chat_id": "chat"},
        },
    )
    monkeypatch.setattr("twag.notifier.can_send_alert", lambda score: True)
    monkeypatch.setattr("twag.notifier.send_ron_alert", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "twag.notifier.send_telegram_alert",
        lambda message, **kwargs: direct.append((message, kwargs)) or True,
    )
    assert notify_high_signal_tweet(
        "1",
        "source",
        "Resolved",
        6,
        ["crypto"],
        "Catalyst dead",
        catalyst_status="resolved",
    )
    assert direct[0][0].endswith("(raw — ron unavailable)")
    assert direct[0][1]["chat_id"] == "chat"
