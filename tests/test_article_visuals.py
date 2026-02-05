"""Tests for article visual selection helper."""

from twag.article_visuals import build_article_visuals


def test_build_article_visuals_orders_top_first_and_filters_noise() -> None:
    top = {
        "url": "https://example.com/top-chart.jpg",
        "kind": "chart",
        "why_important": "Primary quantitative evidence.",
        "key_takeaway": "Capex inflects sharply in 2026.",
    }
    media = [
        {"url": "https://example.com/meme.jpg", "kind": "meme", "short_description": "funny meme"},
        {"url": "https://example.com/top-chart.jpg", "kind": "chart", "chart": {"insight": "duplicate"}},
        {
            "url": "https://example.com/table.jpg",
            "kind": "table",
            "table": {"summary": "Table confirms acceleration"},
        },
        {
            "url": "https://example.com/doc.jpg",
            "kind": "document",
            "prose_summary": "Document provides supporting context.",
        },
    ]

    visuals = build_article_visuals(top_visual=top, media_items=media, max_items=5)

    assert len(visuals) == 3
    assert visuals[0]["is_top"] is True
    assert visuals[0]["url"] == "https://example.com/top-chart.jpg"
    assert visuals[1]["kind"] == "table"
    assert visuals[2]["kind"] == "document"


def test_build_article_visuals_infers_chart_kind_from_payload() -> None:
    media = [
        {
            "url": "https://example.com/inferred-chart.jpg",
            "chart": {"description": "Revenue by quarter"},
        }
    ]
    visuals = build_article_visuals(top_visual=None, media_items=media, max_items=3)
    assert len(visuals) == 1
    assert visuals[0]["kind"] == "chart"


def test_build_article_visuals_promotes_data_like_photo_and_keeps_multiple() -> None:
    media = [
        {
            "url": "https://example.com/photo-chart.jpg",
            "kind": "photo",
            "short_description": "Chart of cloud revenue growth to $120B run-rate",
        },
        {
            "url": "https://example.com/second-chart.jpg",
            "kind": "photo",
            "short_description": "Capex projected to grow 45% YoY with $180B spend",
        },
        {"url": "https://example.com/meme.jpg", "kind": "photo", "short_description": "reaction meme"},
    ]
    visuals = build_article_visuals(top_visual=None, media_items=media, max_items=5)

    assert len(visuals) == 2
    assert visuals[0]["kind"] == "chart"
    assert visuals[1]["kind"] == "chart"
    assert all("meme" not in v["url"] for v in visuals)


def test_build_article_visuals_skips_non_data_top_visual() -> None:
    top = {
        "url": "https://example.com/meme-top.jpg",
        "kind": "photo",
        "why_important": "Funny meme",
        "key_takeaway": "joke image",
    }
    media = [
        {
            "url": "https://example.com/relevant-chart.jpg",
            "kind": "chart",
            "chart": {"insight": "Revenue acceleration by quarter"},
        }
    ]
    visuals = build_article_visuals(top_visual=top, media_items=media, max_items=4)

    assert len(visuals) == 1
    assert visuals[0]["url"] == "https://example.com/relevant-chart.jpg"
    assert visuals[0]["is_top"] is False
