"""Tests for twag.media."""

import json

from twag.media import build_media_context, build_media_summary, parse_media_items


class TestParseMediaItems:
    def test_none_returns_empty(self):
        assert parse_media_items(None) == []

    def test_empty_string_returns_empty(self):
        assert parse_media_items("") == []

    def test_invalid_json_returns_empty(self):
        assert parse_media_items("not json {{{") == []

    def test_dict_with_items_key(self):
        data = {"items": [{"kind": "image", "short_description": "A chart"}]}
        result = parse_media_items(json.dumps(data))
        assert len(result) == 1
        assert result[0]["kind"] == "image"

    def test_flat_list(self):
        data = [{"kind": "chart"}, {"kind": "document"}]
        result = parse_media_items(json.dumps(data))
        assert len(result) == 2

    def test_non_dict_items_filtered(self):
        data = [{"kind": "image"}, "string_item", 42, None]
        result = parse_media_items(json.dumps(data))
        assert len(result) == 1

    def test_unexpected_structure_returns_empty(self):
        # A dict without 'items' key
        data = {"something_else": "value"}
        result = parse_media_items(json.dumps(data))
        assert result == []


class TestBuildMediaSummary:
    def test_prose_summary_priority(self):
        items = [{"prose_summary": "Full analysis of market trends"}]
        assert build_media_summary(items) == "Full analysis of market trends"

    def test_chart_description_fallback(self):
        items = [{"chart": {"description": "S&P 500 weekly"}}]
        assert build_media_summary(items) == "Chart: S&P 500 weekly"

    def test_short_description_last_resort(self):
        items = [{"short_description": "Photo of earnings report"}]
        assert build_media_summary(items) == "Photo of earnings report"

    def test_priority_order(self):
        # prose_summary takes priority even when chart is present
        items = [
            {
                "prose_summary": "Top priority",
                "chart": {"description": "Chart desc"},
                "short_description": "Short desc",
            }
        ]
        assert build_media_summary(items) == "Top priority"

    def test_multiple_items_joined(self):
        items = [
            {"prose_summary": "First"},
            {"short_description": "Second"},
        ]
        assert build_media_summary(items) == "First | Second"

    def test_empty_items(self):
        assert build_media_summary([]) == ""


class TestBuildMediaContext:
    def test_chart_with_insight_and_implication(self):
        items = [
            {
                "kind": "chart",
                "chart": {
                    "description": "YTD returns",
                    "insight": "Tech leads",
                    "implication": "Rotation risk",
                },
            }
        ]
        result = build_media_context(items)
        assert "Media 1 (chart)" in result
        assert "Chart description: YTD returns" in result
        assert "Chart insight: Tech leads" in result
        assert "Chart implication: Rotation risk" in result

    def test_document_with_prose(self):
        items = [{"kind": "document", "prose_text": "Full text of the filing"}]
        result = build_media_context(items)
        assert "Media 1 (document)" in result
        assert "Document text:" in result
        assert "Full text of the filing" in result

    def test_image_with_short_description(self):
        items = [{"kind": "image", "short_description": "Earnings table"}]
        result = build_media_context(items)
        assert "Image description: Earnings table" in result

    def test_multi_media_indexing(self):
        items = [
            {"kind": "chart", "chart": {"description": "Chart 1"}},
            {"kind": "image", "short_description": "Image 2"},
        ]
        result = build_media_context(items)
        assert "Media 1 (chart)" in result
        assert "Media 2 (image)" in result

    def test_empty_item_skipped(self):
        items = [{"kind": "image"}]
        result = build_media_context(items)
        assert result == ""
