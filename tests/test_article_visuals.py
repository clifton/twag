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
