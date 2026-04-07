"""Tests for twag.media — media parsing and formatting utilities."""

import json

from twag.media import build_media_context, build_media_summary, parse_media_items


class TestParseMediaItems:
    def test_none_returns_empty(self):
        assert parse_media_items(None) == []

    def test_empty_string_returns_empty(self):
        assert parse_media_items("") == []

    def test_invalid_json_returns_empty(self):
        assert parse_media_items("not json") == []

    def test_dict_with_items_key(self):
        raw = json.dumps({"items": [{"kind": "image"}, {"kind": "video"}]})
        result = parse_media_items(raw)
        assert len(result) == 2
        assert result[0]["kind"] == "image"

    def test_list_format(self):
        raw = json.dumps([{"kind": "image"}])
        result = parse_media_items(raw)
        assert len(result) == 1

    def test_non_dict_items_filtered(self):
        raw = json.dumps([{"kind": "image"}, "not a dict", 42])
        result = parse_media_items(raw)
        assert len(result) == 1

    def test_dict_without_items_key(self):
        raw = json.dumps({"kind": "image"})
        assert parse_media_items(raw) == []


class TestBuildMediaSummary:
    def test_prose_summary_priority(self):
        items = [{"prose_summary": "A chart showing growth", "short_description": "chart"}]
        assert build_media_summary(items) == "A chart showing growth"

    def test_chart_description_fallback(self):
        items = [{"chart": {"description": "S&P 500 movement"}}]
        assert build_media_summary(items) == "Chart: S&P 500 movement"

    def test_short_description_fallback(self):
        items = [{"short_description": "Market graph"}]
        assert build_media_summary(items) == "Market graph"

    def test_pipe_joining(self):
        items = [
            {"prose_summary": "First"},
            {"prose_summary": "Second"},
        ]
        assert build_media_summary(items) == "First | Second"

    def test_empty_items(self):
        assert build_media_summary([]) == ""

    def test_all_empty_fields(self):
        items = [{"prose_summary": "", "short_description": "", "chart": {}}]
        assert build_media_summary(items) == ""


class TestBuildMediaContext:
    def test_kind_header(self):
        items = [{"kind": "chart", "short_description": "Line graph"}]
        result = build_media_context(items)
        assert "Media 1 (chart)" in result

    def test_prose_text_branch(self):
        items = [{"prose_text": "Document content here"}]
        result = build_media_context(items)
        assert "Document text:" in result
        assert "Document content here" in result

    def test_chart_branch(self):
        items = [{"chart": {"description": "SPY chart", "insight": "Bullish", "implication": "Buy signal"}}]
        result = build_media_context(items)
        assert "Chart description: SPY chart" in result
        assert "Chart insight: Bullish" in result
        assert "Chart implication: Buy signal" in result

    def test_short_description_branch(self):
        items = [{"short_description": "A photo"}]
        result = build_media_context(items)
        assert "Image description: A photo" in result

    def test_default_kind_is_image(self):
        items = [{"short_description": "something"}]
        result = build_media_context(items)
        assert "Media 1 (image)" in result

    def test_multi_media(self):
        items = [
            {"kind": "chart", "short_description": "First"},
            {"kind": "image", "short_description": "Second"},
        ]
        result = build_media_context(items)
        assert "Media 1 (chart)" in result
        assert "Media 2 (image)" in result

    def test_empty_items(self):
        assert build_media_context([]) == ""
