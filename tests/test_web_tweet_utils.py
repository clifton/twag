"""Tests for twag.web.tweet_utils — URL parsing, HTML decoding, date handling."""

from datetime import datetime, timezone

from twag.web.tweet_utils import (
    decode_html_entities,
    parse_created_at,
    quote_embed_from_row,
)


class TestParseCreatedAt:
    def test_none_returns_none(self):
        assert parse_created_at(None) is None

    def test_datetime_passthrough(self):
        dt = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        assert parse_created_at(dt) is dt

    def test_iso_string(self):
        result = parse_created_at("2025-01-15T12:00:00+00:00")
        assert result == datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    def test_z_suffix(self):
        result = parse_created_at("2025-01-15T12:00:00Z")
        assert result == datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    def test_invalid_returns_none(self):
        assert parse_created_at("not a date") is None


class TestDecodeHtmlEntities:
    def test_none_returns_none(self):
        assert decode_html_entities(None) is None

    def test_html_entities_decoded(self):
        assert decode_html_entities("&amp; &lt; &gt;") == "& < >"

    def test_clean_string_passthrough(self):
        assert decode_html_entities("hello") == "hello"


class TestQuoteEmbedFromRow:
    def test_field_mapping(self):
        row = {
            "id": "123",
            "author_handle": "user",
            "author_name": "User Name",
            "content": "Hello &amp; world",
            "created_at": "2025-01-15T12:00:00Z",
        }
        result = quote_embed_from_row(row)
        assert result["id"] == "123"
        assert result["author_handle"] == "user"
        assert result["author_name"] == "User Name"
        assert result["content"] == "Hello & world"

    def test_created_at_formatting(self):
        row = {
            "id": "123",
            "author_handle": "user",
            "author_name": "Name",
            "content": "text",
            "created_at": "2025-01-15T12:00:00Z",
        }
        result = quote_embed_from_row(row)
        assert result["created_at"] is not None
        # Should be ISO format
        assert "2025-01-15" in result["created_at"]

    def test_none_created_at(self):
        row = {
            "id": "123",
            "author_handle": "user",
            "author_name": "Name",
            "content": "text",
            "created_at": None,
        }
        result = quote_embed_from_row(row)
        assert result["created_at"] is None
