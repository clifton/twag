"""Tests for twag.media — media parsing and formatting."""

import json

from twag.media import build_media_context, build_media_summary, parse_media_items


def test_parse_media_items_none():
    assert parse_media_items(None) == []


def test_parse_media_items_empty_string():
    assert parse_media_items("") == []


def test_parse_media_items_valid_list():
    items = [{"kind": "image", "short_description": "A chart"}]
    assert parse_media_items(json.dumps(items)) == items


def test_parse_media_items_wrapped_in_items_key():
    data = {"items": [{"kind": "video"}]}
    assert parse_media_items(json.dumps(data)) == [{"kind": "video"}]


def test_parse_media_items_malformed_json():
    assert parse_media_items("not json{") == []


def test_parse_media_items_non_dict_items_filtered():
    raw = json.dumps([{"kind": "image"}, "bad", 42])
    result = parse_media_items(raw)
    assert result == [{"kind": "image"}]


def test_parse_media_items_dict_without_items_key():
    raw = json.dumps({"other": "data"})
    assert parse_media_items(raw) == []


def test_build_media_summary_prose():
    items = [{"prose_summary": "GDP up 3%"}, {"prose_summary": "Inflation at 2%"}]
    assert build_media_summary(items) == "GDP up 3% | Inflation at 2%"


def test_build_media_summary_chart():
    items = [{"chart": {"description": "S&P 500 performance"}}]
    assert build_media_summary(items) == "Chart: S&P 500 performance"


def test_build_media_summary_short_description():
    items = [{"short_description": "A screenshot"}]
    assert build_media_summary(items) == "A screenshot"


def test_build_media_summary_priority_order():
    # prose_summary takes priority over chart and short_description
    item = {"prose_summary": "prose", "chart": {"description": "chart"}, "short_description": "short"}
    assert build_media_summary([item]) == "prose"


def test_build_media_summary_empty():
    assert build_media_summary([]) == ""


def test_build_media_context_prose_text():
    items = [{"kind": "document", "prose_text": "Full document text here."}]
    result = build_media_context(items)
    assert "Media 1 (document)" in result
    assert "Document text:" in result
    assert "Full document text here." in result


def test_build_media_context_chart():
    items = [
        {"kind": "image", "chart": {"description": "Line chart", "insight": "Rising trend", "implication": "Bullish"}}
    ]
    result = build_media_context(items)
    assert "Chart description: Line chart" in result
    assert "Chart insight: Rising trend" in result
    assert "Chart implication: Bullish" in result


def test_build_media_context_short_description():
    items = [{"short_description": "A meme image"}]
    result = build_media_context(items)
    assert "Media 1 (image)" in result
    assert "Image description: A meme image" in result


def test_build_media_context_empty_items():
    assert build_media_context([]) == ""


def test_build_media_context_multiple_items():
    items = [
        {"kind": "image", "short_description": "First"},
        {"kind": "video", "short_description": "Second"},
    ]
    result = build_media_context(items)
    assert "Media 1 (image)" in result
    assert "Media 2 (video)" in result
