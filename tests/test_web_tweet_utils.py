"""Tests for twag.web.tweet_utils — parsing, link extraction, HTML decoding."""

from datetime import datetime, timezone

from twag.web.tweet_utils import (
    decode_html_entities,
    extract_tweet_links,
    normalize_links_for_display,
    parse_created_at,
    parse_tweet_id_from_url,
    remove_tweet_links,
)


def test_parse_created_at_none():
    assert parse_created_at(None) is None


def test_parse_created_at_datetime_passthrough():
    dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert parse_created_at(dt) is dt


def test_parse_created_at_iso_string():
    result = parse_created_at("2025-01-15T10:30:00+00:00")
    assert result == datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc)


def test_parse_created_at_z_suffix():
    result = parse_created_at("2025-01-15T10:30:00Z")
    assert result == datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc)


def test_parse_created_at_invalid():
    assert parse_created_at("not a date") is None


def test_extract_tweet_links_finds_x_urls():
    text = "Check this https://x.com/user/status/12345 and https://twitter.com/other/status/67890"
    links = extract_tweet_links(text)
    assert len(links) == 2
    assert links[0][0] == "12345"
    assert links[1][0] == "67890"


def test_extract_tweet_links_no_matches():
    assert extract_tweet_links("no links here") == []


def test_extract_tweet_links_mobile_url():
    text = "https://mobile.x.com/user/status/99999"
    links = extract_tweet_links(text)
    assert len(links) == 1
    assert links[0][0] == "99999"


def test_remove_tweet_links_removes_matching_ids():
    text = "before https://x.com/user/status/123 after"
    links = extract_tweet_links(text)
    result = remove_tweet_links(text, links, {"123"})
    assert "https://x.com" not in result
    assert "before" in result
    assert "after" in result


def test_remove_tweet_links_keeps_non_matching():
    text = "before https://x.com/user/status/123 after"
    links = extract_tweet_links(text)
    result = remove_tweet_links(text, links, {"999"})
    assert "https://x.com/user/status/123" in result


def test_normalize_links_for_display_passes_already_expanded(monkeypatch):
    monkeypatch.setattr(
        "twag.link_utils._expand_short_url",
        lambda _url: (_ for _ in ()).throw(AssertionError("should not expand")),
    )
    result = normalize_links_for_display(
        tweet_id="100",
        text="Hello https://t.co/abc",
        links=[{"url": "https://t.co/abc", "expanded_url": "https://example.com", "display_url": "example.com"}],
    )
    assert "https://example.com" in result.display_text


def test_parse_tweet_id_from_url_valid():
    assert parse_tweet_id_from_url("https://x.com/user/status/12345") == "12345"


def test_parse_tweet_id_from_url_none():
    assert parse_tweet_id_from_url(None) is None


def test_parse_tweet_id_from_url_non_tweet():
    assert parse_tweet_id_from_url("https://example.com") is None


def test_decode_html_entities_none():
    assert decode_html_entities(None) is None


def test_decode_html_entities_basic():
    assert decode_html_entities("A &gt; B &amp; C") == "A > B & C"


def test_decode_html_entities_clean():
    assert decode_html_entities("no entities") == "no entities"
