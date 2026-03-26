"""Extended tests for twag.link_utils — helper functions not covered by test_link_utils.py."""

from twag.link_utils import (
    clean_url_candidate,
    extract_urls_from_text,
    parse_tweet_status_id,
    remove_urls_from_text,
    replace_urls_in_text,
)


class TestParseTweetStatusId:
    def test_twitter_url(self):
        assert parse_tweet_status_id("https://twitter.com/user/status/123456") == "123456"

    def test_x_url(self):
        assert parse_tweet_status_id("https://x.com/user/status/789") == "789"

    def test_mobile_url(self):
        assert parse_tweet_status_id("https://mobile.x.com/user/status/111") == "111"

    def test_www_url(self):
        assert parse_tweet_status_id("https://www.twitter.com/user/status/222") == "222"

    def test_with_query_params(self):
        assert parse_tweet_status_id("https://x.com/user/status/333?s=20") == "333"

    def test_none_input(self):
        assert parse_tweet_status_id(None) is None

    def test_non_twitter_url(self):
        assert parse_tweet_status_id("https://github.com/user/repo") is None

    def test_empty_string(self):
        assert parse_tweet_status_id("") is None

    def test_i_web_path(self):
        assert parse_tweet_status_id("https://x.com/i/web/status/444") == "444"


class TestExtractUrlsFromText:
    def test_single_url(self):
        result = extract_urls_from_text("Check out https://example.com today")
        assert result == ["https://example.com"]

    def test_multiple_urls(self):
        text = "Visit https://a.com and http://b.com for more"
        result = extract_urls_from_text(text)
        assert len(result) == 2

    def test_deduplicates(self):
        text = "https://same.com twice https://same.com"
        assert len(extract_urls_from_text(text)) == 1

    def test_none_input(self):
        assert extract_urls_from_text(None) == []

    def test_empty_string(self):
        assert extract_urls_from_text("") == []

    def test_no_urls(self):
        assert extract_urls_from_text("no links here") == []


class TestCleanUrlCandidate:
    def test_strips_trailing_punctuation(self):
        assert clean_url_candidate("https://example.com).") == "https://example.com"

    def test_strips_trailing_comma(self):
        assert clean_url_candidate("https://example.com,") == "https://example.com"

    def test_strips_whitespace(self):
        assert clean_url_candidate("  https://example.com  ") == "https://example.com"

    def test_no_change_for_clean_url(self):
        assert clean_url_candidate("https://example.com/path") == "https://example.com/path"


class TestRemoveUrlsFromText:
    def test_removes_url(self):
        text = "Hello https://remove.me world"
        result = remove_urls_from_text(text, {"https://remove.me"})
        assert "remove.me" not in result
        assert "Hello" in result
        assert "world" in result

    def test_empty_urls_no_change(self):
        assert remove_urls_from_text("text here", set()) == "text here"

    def test_empty_text(self):
        assert remove_urls_from_text("", {"https://x.com"}) == ""

    def test_multiline(self):
        text = "line one https://remove.me\nline two"
        result = remove_urls_from_text(text, {"https://remove.me"})
        assert "line one" in result
        assert "line two" in result
        assert "remove.me" not in result


class TestReplaceUrlsInText:
    def test_replaces_url(self):
        text = "Visit https://t.co/abc for info"
        result = replace_urls_in_text(text, {"https://t.co/abc": "https://example.com/full"})
        assert "https://example.com/full" in result
        assert "t.co" not in result

    def test_empty_replacements(self):
        assert replace_urls_in_text("text", {}) == "text"

    def test_empty_text(self):
        assert replace_urls_in_text("", {"a": "b"}) == ""

    def test_multiline_replacement(self):
        text = "first https://t.co/x\nsecond https://t.co/y"
        result = replace_urls_in_text(text, {"https://t.co/x": "https://a.com", "https://t.co/y": "https://b.com"})
        assert "https://a.com" in result
        assert "https://b.com" in result


class TestIsShortenerUrl:
    def test_tco_is_shortener(self):
        from twag.link_utils import _is_shortener_url

        assert _is_shortener_url("https://t.co/abc123") is True

    def test_regular_url_is_not(self):
        from twag.link_utils import _is_shortener_url

        assert _is_shortener_url("https://github.com/user/repo") is False

    def test_empty_string(self):
        from twag.link_utils import _is_shortener_url

        assert _is_shortener_url("") is False
