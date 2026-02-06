"""Tests for digest rendering of structured article sections."""

from datetime import datetime, timezone

from twag.db import (
    get_connection,
    init_db,
    insert_tweet,
    update_tweet_article,
    update_tweet_processing,
)
from twag.renderer import render_digest


def test_render_digest_uses_labeled_article_sections(monkeypatch, tmp_path):
    db_path = tmp_path / "twag_renderer_article_sections.db"
    init_db(db_path)

    now = datetime.now(timezone.utc)
    digest_date = now.strftime("%Y-%m-%d")

    with get_connection(db_path) as conn:
        inserted = insert_tweet(
            conn,
            tweet_id="31001",
            author_handle="undrvalue",
            content="Google's $180B AI capex guidance is a regime shift.",
            created_at=now,
            source="test",
            has_link=True,
            is_x_article=True,
            article_title="Google's $180 Billion Bet",
            article_preview="Preview",
            article_text="Long body",
        )
        assert inserted is True

        update_tweet_processing(
            conn,
            tweet_id="31001",
            relevance_score=9.0,
            categories=["capex", "tech_business", "ai_advancement"],
            summary=(
                "Deep dive into Google's record $180B 2026 capex guidance and "
                "the compute-to-ROI playbook across cloud and ads."
            ),
            signal_tier="high_signal",
            tickers=["GOOGL", "MSFT", "META"],
        )
        update_tweet_article(
            conn,
            tweet_id="31001",
            article_summary_short=(
                "Google's $180B 2026 capex guidance is historically large, but "
                "backlog visibility and ad monetization data suggest demand-driven deployment."
            ),
            primary_points=[
                {
                    "point": "Capex magnitude is unprecedented for a single company.",
                    "reasoning": "Real-dollar levels rival peak dotcom telecom infrastructure spend.",
                    "evidence": "Guide implies nearly 2x versus the prior year run-rate.",
                },
                {"point": "", "reasoning": "invalid and should be ignored", "evidence": "n/a"},
            ],
            actionable_items=[
                {
                    "action": "Monitor GCP growth and backlog durability each quarter.",
                    "trigger": "Cloud growth drops below 30% while backlog growth stalls.",
                    "horizon": "medium_term",
                    "confidence": 0.7,
                    "tickers": ["GOOGL", "AMZN", "MSFT"],
                },
                {"action": "", "trigger": "invalid and should be ignored"},
            ],
            top_visual={
                "url": "https://pbs.twimg.com/media/HAXmiH6acAEiywu.jpg",
                "kind": "chart",
                "why_important": "Core chart showing the acceleration profile into 2026.",
                "key_takeaway": "Capex trend inflects sharply after 2023 and spikes in 2026.",
            },
            set_top_visual=True,
            processed_at=now.isoformat(),
        )
        conn.commit()

    monkeypatch.setattr("twag.renderer.get_connection", lambda readonly=False: get_connection(db_path))
    output_path = tmp_path / "digest.md"
    content = render_digest(date=digest_date, min_score=5.0, output_path=output_path)

    assert "🧾 **Article Summary:**" in content
    assert "📌 **Primary Points:**" in content
    assert "- **1. Capex magnitude is unprecedented for a single company.**" in content
    assert "- **Why:** Real-dollar levels rival peak dotcom telecom infrastructure spend." in content
    assert "- **Evidence:** Guide implies nearly 2x versus the prior year run-rate." in content
    assert "✅ **Actionable Items:**" in content
    assert "- **1. Monitor GCP growth and backlog durability each quarter.**" in content
    assert "- **Trigger:** Cloud growth drops below 30% while backlog growth stalls." in content
    assert "- **Horizon:** medium term" in content
    assert "- **Confidence:** 0.7" in content
    assert "- **Tickers:** GOOGL, AMZN, MSFT" in content
    assert "(trigger:" not in content
    assert "invalid and should be ignored" not in content
    assert "🖼️ **Visuals:**" in content
    assert "- **1. chart (top)**" in content
    assert "- **Key takeaway:** Capex trend inflects sharply after 2023 and spikes in 2026." in content
    assert "- **Why:** Core chart showing the acceleration profile into 2026." in content
    assert "- **URL:** https://pbs.twimg.com/media/HAXmiH6acAEiywu.jpg" in content
