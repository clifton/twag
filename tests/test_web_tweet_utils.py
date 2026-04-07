"""Tests for twag.web.tweet_utils — URL parsing, HTML decoding, date handling."""

from datetime import datetime, timezone

from twag.web.tweet_utils import (
    decode_html_entities,
    extract_tweet_links,
    parse_created_at,
    quote_embed_from_row,
    remove_tweet_links,
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


class TestExtractTweetLinks:
    def test_x_com_url(self):
        text = "Check https://x.com/user/status/123456789"
        result = extract_tweet_links(text)
        assert len(result) == 1
        assert result[0][0] == "123456789"

    def test_twitter_com_url(self):
        text = "See https://twitter.com/user/status/987654321"
        result = extract_tweet_links(text)
        assert len(result) == 1
        assert result[0][0] == "987654321"

    def test_mobile_url(self):
        text = "Link https://mobile.x.com/user/status/111222333"
        result = extract_tweet_links(text)
        assert len(result) == 1
        assert result[0][0] == "111222333"

    def test_no_matches(self):
        assert extract_tweet_links("no links here") == []

    def test_multiple_links(self):
        text = "A https://x.com/a/status/111 B https://x.com/b/status/222"
        result = extract_tweet_links(text)
        assert len(result) == 2

    def test_url_with_query_params(self):
        text = "https://x.com/user/status/555?s=20&t=abc"
        result = extract_tweet_links(text)
        assert len(result) == 1
        assert result[0][0] == "555"


class TestRemoveTweetLinks:
    def test_removes_matching_ids(self):
        text = "Hello https://x.com/user/status/123 world"
        links = [("123", "https://x.com/user/status/123")]
        result = remove_tweet_links(text, links, remove_ids={"123"})
        assert "https://x.com" not in result
        assert "Hello" in result
        assert "world" in result

    def test_preserves_non_matching(self):
        text = "Hello https://x.com/user/status/123 world"
        links = [("123", "https://x.com/user/status/123")]
        result = remove_tweet_links(text, links, remove_ids={"999"})
        assert "https://x.com/user/status/123" in result

    def test_whitespace_collapse(self):
        text = "Hello   https://x.com/user/status/123   world"
        links = [("123", "https://x.com/user/status/123")]
        result = remove_tweet_links(text, links, remove_ids={"123"})
        # Should collapse multiple spaces
        assert "  " not in result


class TestDecodeHtmlEntities:
    def test_none_returns_none(self):
        assert decode_html_entities(None) is None

    def test_html_entities(self):
        assert decode_html_entities("&amp; &lt; &gt;") == "& < >"

    def test_plain_text_unchanged(self):
        assert decode_html_entities("hello world") == "hello world"

    def test_numeric_entities(self):
        assert decode_html_entities("&#39;") == "'"


class TestQuoteEmbedFromRow:
    def _make_row(self, **kwargs):
        """Create a dict-like row object."""
        defaults = {
            "id": "123",
            "author_handle": "user",
            "author_name": "User Name",
            "content": "tweet content",
            "created_at": "2025-01-15T12:00:00Z",
        }
        defaults.update(kwargs)
        return defaults

    def test_basic_mapping(self):
        row = self._make_row()
        result = quote_embed_from_row(row)
        assert result["id"] == "123"
        assert result["author_handle"] == "user"
        assert result["author_name"] == "User Name"
        assert result["content"] == "tweet content"

    def test_created_at_formatting(self):
        row = self._make_row(created_at="2025-01-15T12:00:00Z")
        result = quote_embed_from_row(row)
        assert result["created_at"] is not None
        assert "2025-01-15" in result["created_at"]

    def test_none_created_at(self):
        row = self._make_row(created_at=None)
        result = quote_embed_from_row(row)
        assert result["created_at"] is None

    def test_html_entities_decoded(self):
        row = self._make_row(content="&amp; earnings")
        result = quote_embed_from_row(row)
        assert result["content"] == "& earnings"
