"""Tests for X-native article extraction and processing helpers."""

import json
from datetime import datetime, timezone
from pathlib import Path

from twag.db import (
    get_connection,
    get_feed_tweets,
    init_db,
    insert_tweet,
    update_tweet_article,
    update_tweet_processing,
)
from twag.fetcher import Tweet
from twag.processor import _select_article_top_visual


def _load_real_article_fixture() -> dict:
    fixture_path = Path(__file__).parent / "fixtures" / "tweet_2019488673935552978.json"
    with fixture_path.open() as f:
        return json.load(f)


def test_real_world_x_article_fixture_parses() -> None:
    data = _load_real_article_fixture()

    tweet = Tweet.from_bird_json(data)

    assert tweet.id == "2019488673935552978"
    assert tweet.is_x_article is True
    assert tweet.article_title == "Google's $180 Billion Bet: Is This the Top?"
    assert tweet.article_text is not None
    assert len(tweet.article_text) > 5000
    assert tweet.has_link is True
    assert tweet.has_media is True
    assert any(item.get("source", "").startswith("article") for item in tweet.media_items)


def test_x_article_text_fallback_from_blocks() -> None:
    payload = {
        "id": "article-fallback",
        "author": {"username": "author1"},
        "_raw": {
            "article": {
                "article_results": {
                    "result": {
                        "title": "Fallback title",
                        "preview_text": "Preview",
                        "content_state": {
                            "blocks": [
                                {"text": "Paragraph one."},
                                {"text": "  "},
                                {"text": "Paragraph two."},
                            ]
                        },
                    }
                }
            }
        },
    }

    tweet = Tweet.from_bird_json(payload)

    assert tweet.is_x_article is True
    assert tweet.article_text == "Paragraph one.\nParagraph two."
    assert tweet.article_title == "Fallback title"
    assert tweet.article_preview == "Preview"


def test_top_visual_selector_prefers_chart_and_excludes_noise() -> None:
    media_items = [
        {
            "url": "https://example.com/meme.jpg",
            "kind": "meme",
            "short_description": "funny meme",
        },
        {
            "url": "https://example.com/chart.jpg",
            "kind": "chart",
            "chart": {
                "description": "Google capex by year 2016 to 2026",
                "insight": "2026 capex rises to 180B from 98B in 2025",
                "implication": "capex cycle still expanding",
            },
        },
    ]

    selected = _select_article_top_visual(
        media_items,
        article_title="Google capex outlook",
        article_summary="Capex ramps sharply into 2026.",
        primary_points=[{"point": "Capex jumps", "reasoning": "Demand remains high", "evidence": "$180B in 2026"}],
    )

    assert selected is not None
    assert selected["url"] == "https://example.com/chart.jpg"
    assert selected["kind"] == "chart"


def test_top_visual_selector_omits_irrelevant_non_chart() -> None:
    media_items = [
        {
            "url": "https://example.com/photo.jpg",
            "kind": "photo",
            "short_description": "office selfie",
        },
        {
            "url": "https://example.com/screen.jpg",
            "kind": "screenshot",
            "prose_summary": "great vibes only",
        },
    ]

    selected = _select_article_top_visual(
        media_items,
        article_title="Cloud margins and capex",
        article_summary="Detailed numbers on cloud growth and backlog.",
    )

    assert selected is None


def test_article_fields_round_trip_in_feed(tmp_path) -> None:
    db_path = tmp_path / "article_roundtrip.db"
    init_db(db_path)

    with get_connection(db_path) as conn:
        inserted = insert_tweet(
            conn,
            tweet_id="article-1",
            author_handle="analyst",
            content="Long-form article tweet",
            created_at=datetime.now(timezone.utc),
            source="test",
            has_link=True,
            is_x_article=True,
            article_title="Capex Deep Dive",
            article_preview="Preview line",
            article_text="Full text body",
        )
        assert inserted is True

        update_tweet_processing(
            conn,
            tweet_id="article-1",
            relevance_score=8.5,
            categories=["tech_business"],
            summary="High-signal capex thesis",
            signal_tier="high_signal",
            tickers=["GOOGL"],
        )
        update_tweet_article(
            conn,
            "article-1",
            article_summary_short="Short article summary",
            primary_points=[{"point": "P1", "reasoning": "R1", "evidence": "E1"}],
            actionable_items=[{"action": "Monitor GOOGL", "trigger": "Q/Q cloud growth > 40%"}],
            top_visual=None,
            set_top_visual=True,
            processed_at=datetime.now(timezone.utc).isoformat(),
        )
        conn.commit()

        tweets = get_feed_tweets(conn, limit=10)

    assert len(tweets) == 1
    tweet = tweets[0]
    assert tweet.is_x_article is True
    assert tweet.article_title == "Capex Deep Dive"
    assert tweet.article_summary_short == "Short article summary"
    assert tweet.link_summary == "Short article summary"
    assert len(tweet.article_primary_points) == 1
    assert len(tweet.article_action_items) == 1
    assert tweet.article_top_visual is None
