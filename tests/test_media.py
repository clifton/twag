"""Tests for twag.media."""

import json

from twag.media import build_media_context, build_media_summary, parse_media_items


class TestParseMediaItems:
    def test_none_input(self):
        assert parse_media_items(None) == []

    def test_empty_string(self):
        assert parse_media_items("") == []

    def test_invalid_json(self):
        assert parse_media_items("not json") == []

    def test_dict_with_items_key(self):
        data = {"items": [{"kind": "image", "short_description": "a chart"}]}
        result = parse_media_items(json.dumps(data))
        assert len(result) == 1
        assert result[0]["kind"] == "image"

    def test_bare_list(self):
        data = [{"kind": "photo"}, {"kind": "video"}]
        result = parse_media_items(json.dumps(data))
        assert len(result) == 2

    def test_non_dict_items_filtered(self):
        data = [{"kind": "image"}, "not a dict", 42, {"kind": "video"}]
        result = parse_media_items(json.dumps(data))
        assert len(result) == 2

    def test_dict_without_items_key(self):
        data = {"foo": "bar"}
        result = parse_media_items(json.dumps(data))
        assert result == []


class TestBuildMediaSummary:
    def test_prose_summary_priority(self):
        items = [
            {"prose_summary": "Revenue up 20%", "short_description": "a chart", "chart": {"description": "bar chart"}}
        ]
        assert build_media_summary(items) == "Revenue up 20%"

    def test_chart_fallback(self):
        items = [{"chart": {"description": "S&P 500 performance"}}]
        assert build_media_summary(items) == "Chart: S&P 500 performance"

    def test_short_description_fallback(self):
        items = [{"short_description": "Company logo"}]
        assert build_media_summary(items) == "Company logo"

    def test_multiple_items_joined(self):
        items = [
            {"prose_summary": "First item"},
            {"short_description": "Second item"},
        ]
        assert build_media_summary(items) == "First item | Second item"

    def test_empty_items(self):
        assert build_media_summary([]) == ""

    def test_item_with_no_content(self):
        items = [{"kind": "image"}]
        assert build_media_summary(items) == ""


class TestBuildMediaContext:
    def test_kind_header(self):
        items = [{"kind": "screenshot", "short_description": "a UI"}]
        result = build_media_context(items)
        assert "Media 1 (screenshot)" in result

    def test_prose_text_path(self):
        items = [{"kind": "document", "prose_text": "Full document content here"}]
        result = build_media_context(items)
        assert "Document text:" in result
        assert "Full document content here" in result

    def test_chart_path_with_insight_and_implication(self):
        items = [
            {
                "kind": "chart",
                "chart": {
                    "description": "GDP growth",
                    "insight": "Trending up",
                    "implication": "Bullish signal",
                },
            }
        ]
        result = build_media_context(items)
        assert "Chart description: GDP growth" in result
        assert "Chart insight: Trending up" in result
        assert "Chart implication: Bullish signal" in result

    def test_short_description_path(self):
        items = [{"kind": "image", "short_description": "A corporate headshot"}]
        result = build_media_context(items)
        assert "Image description: A corporate headshot" in result

    def test_multi_item_output(self):
        items = [
            {"kind": "chart", "chart": {"description": "Chart A"}},
            {"kind": "image", "short_description": "Image B"},
        ]
        result = build_media_context(items)
        assert "Media 1 (chart)" in result
        assert "Media 2 (image)" in result

    def test_default_kind(self):
        items = [{"short_description": "no kind set"}]
        result = build_media_context(items)
        assert "Media 1 (image)" in result

    def test_empty_items(self):
        assert build_media_context([]) == ""
