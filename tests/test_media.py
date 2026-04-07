"""Tests for twag.media — media parsing and formatting."""

import json

from twag.media import build_media_context, build_media_summary, parse_media_items


class TestParseMediaItems:
    def test_none_input(self):
        assert parse_media_items(None) == []

    def test_empty_string(self):
        assert parse_media_items("") == []

    def test_invalid_json(self):
        assert parse_media_items("not json{") == []

    def test_dict_with_items_key(self):
        data = {"items": [{"kind": "photo"}, {"kind": "video"}]}
        result = parse_media_items(json.dumps(data))
        assert len(result) == 2
        assert result[0]["kind"] == "photo"

    def test_list_format(self):
        data = [{"kind": "photo"}, {"kind": "video"}]
        result = parse_media_items(json.dumps(data))
        assert len(result) == 2

    def test_non_dict_items_filtered(self):
        data = [{"kind": "photo"}, "not_a_dict", 42, {"kind": "video"}]
        result = parse_media_items(json.dumps(data))
        assert len(result) == 2

    def test_unexpected_structure(self):
        # A dict without "items" key and not a list
        assert parse_media_items(json.dumps({"foo": "bar"})) == []

    def test_empty_items(self):
        assert parse_media_items(json.dumps({"items": []})) == []
        assert parse_media_items(json.dumps([])) == []


class TestBuildMediaSummary:
    def test_empty_list(self):
        assert build_media_summary([]) == ""

    def test_prose_summary_priority(self):
        items = [{"prose_summary": "A chart showing growth", "short_description": "chart img"}]
        assert build_media_summary(items) == "A chart showing growth"

    def test_chart_description_fallback(self):
        items = [{"chart": {"description": "S&P 500 performance"}}]
        assert build_media_summary(items) == "Chart: S&P 500 performance"

    def test_short_description_fallback(self):
        items = [{"short_description": "a logo"}]
        assert build_media_summary(items) == "a logo"

    def test_pipe_joining(self):
        items = [
            {"prose_summary": "First"},
            {"prose_summary": "Second"},
        ]
        assert build_media_summary(items) == "First | Second"

    def test_empty_fields_skipped(self):
        items = [{"prose_summary": "", "short_description": "", "chart": {}}]
        assert build_media_summary(items) == ""


class TestBuildMediaContext:
    def test_empty_list(self):
        assert build_media_context([]) == ""

    def test_kind_header(self):
        items = [{"kind": "photo", "short_description": "a dog"}]
        result = build_media_context(items)
        assert "Media 1 (photo)" in result
        assert "Image description: a dog" in result

    def test_prose_text_branch(self):
        items = [{"prose_text": "Full document text here", "kind": "document"}]
        result = build_media_context(items)
        assert "Document text:" in result
        assert "Full document text here" in result

    def test_chart_branch(self):
        items = [
            {
                "kind": "image",
                "chart": {
                    "description": "Revenue chart",
                    "insight": "Revenue grew 20%",
                    "implication": "Strong quarter ahead",
                },
            }
        ]
        result = build_media_context(items)
        assert "Chart description: Revenue chart" in result
        assert "Chart insight: Revenue grew 20%" in result
        assert "Chart implication: Strong quarter ahead" in result

    def test_multi_media_formatting(self):
        items = [
            {"kind": "photo", "short_description": "first"},
            {"kind": "video", "short_description": "second"},
        ]
        result = build_media_context(items)
        assert "Media 1 (photo)" in result
        assert "Media 2 (video)" in result
        assert "\n\n" in result  # sections separated by blank line

    def test_default_kind(self):
        items = [{"short_description": "no kind specified"}]
        result = build_media_context(items)
        assert "Media 1 (image)" in result
