"""Tests for twag.media — parse_media_items, build_media_summary, build_media_context."""

from twag.media import build_media_context, build_media_summary, parse_media_items


class TestParseMediaItems:
    def test_none_returns_empty(self):
        assert parse_media_items(None) == []

    def test_empty_string_returns_empty(self):
        assert parse_media_items("") == []

    def test_malformed_json_returns_empty(self):
        assert parse_media_items("{not json") == []

    def test_bare_list(self):
        raw = '[{"kind": "chart"}, {"kind": "image"}]'
        result = parse_media_items(raw)
        assert len(result) == 2
        assert result[0]["kind"] == "chart"

    def test_wrapped_items(self):
        raw = '{"items": [{"kind": "chart"}]}'
        result = parse_media_items(raw)
        assert len(result) == 1
        assert result[0]["kind"] == "chart"

    def test_skips_non_dict_items(self):
        raw = '[{"kind": "chart"}, "not a dict", 42, null]'
        result = parse_media_items(raw)
        assert len(result) == 1

    def test_dict_without_items_key(self):
        raw = '{"kind": "chart"}'
        result = parse_media_items(raw)
        assert result == []


class TestBuildMediaSummary:
    def test_prefers_prose_summary(self):
        items = [{"prose_summary": "A detailed summary", "short_description": "short"}]
        assert build_media_summary(items) == "A detailed summary"

    def test_falls_back_to_chart_description(self):
        items = [{"chart": {"description": "SP500 chart"}}]
        assert build_media_summary(items) == "Chart: SP500 chart"

    def test_falls_back_to_short_description(self):
        items = [{"short_description": "Some image"}]
        assert build_media_summary(items) == "Some image"

    def test_joins_multiple(self):
        items = [{"prose_summary": "First"}, {"short_description": "Second"}]
        assert build_media_summary(items) == "First | Second"

    def test_empty_items(self):
        assert build_media_summary([]) == ""

    def test_skips_empty_fields(self):
        items = [{"prose_summary": "", "short_description": "fallback"}]
        assert build_media_summary(items) == "fallback"


class TestBuildMediaContext:
    def test_prose_text_path(self):
        items = [{"kind": "document", "prose_text": "Full document text here"}]
        result = build_media_context(items)
        assert "Media 1 (document)" in result
        assert "Document text:" in result
        assert "Full document text here" in result

    def test_chart_path(self):
        items = [{"kind": "chart", "chart": {"description": "SP500", "insight": "Bullish", "implication": "Buy"}}]
        result = build_media_context(items)
        assert "Media 1 (chart)" in result
        assert "Chart description: SP500" in result
        assert "Chart insight: Bullish" in result
        assert "Chart implication: Buy" in result

    def test_short_description_fallback(self):
        items = [{"kind": "image", "short_description": "A photo"}]
        result = build_media_context(items)
        assert "Image description: A photo" in result

    def test_empty_items(self):
        assert build_media_context([]) == ""

    def test_multiple_items_numbered(self):
        items = [
            {"kind": "chart", "chart": {"description": "First chart"}},
            {"kind": "image", "short_description": "Second image"},
        ]
        result = build_media_context(items)
        assert "Media 1 (chart)" in result
        assert "Media 2 (image)" in result

    def test_default_kind_is_image(self):
        items = [{"short_description": "no kind field"}]
        result = build_media_context(items)
        assert "Media 1 (image)" in result
