from twag.link_utils import (
    clean_url_candidate,
    expand_links_in_place,
    extract_urls_from_text,
    normalize_tweet_links,
    parse_tweet_status_id,
    remove_urls_from_text,
)


def test_normalize_tweet_links_expands_short_urls_without_structured_links(monkeypatch):
    mapping = {
        "https://t.co/self": "https://x.com/tom_doerr/status/2019486959219913208",
        "https://t.co/ext": "https://github.com/aliasvault/aliasvault",
    }

    monkeypatch.setattr("twag.link_utils._expand_short_url", lambda url: mapping.get(url, url))

    result = normalize_tweet_links(
        tweet_id="2019486959219913208",
        text="Password manager with email aliasing and built-in server\n\nhttps://t.co/self https://t.co/ext",
        links=None,
    )

    assert result.display_text == (
        "Password manager with email aliasing and built-in server\nhttps://github.com/aliasvault/aliasvault"
    )
    assert result.inline_tweet_links == []
    assert result.external_links == [
        {
            "url": "https://github.com/aliasvault/aliasvault",
            "display_url": "github.com/aliasvault/aliasvault",
            "domain": "github.com",
        }
    ]


def test_normalize_tweet_links_drops_unresolved_short_link_for_media(monkeypatch):
    monkeypatch.setattr("twag.link_utils._expand_short_url", lambda url: url)

    result = normalize_tweet_links(
        tweet_id="2018651828423135467",
        text="Crazy how Nvidia GPUs went to the moon. https://t.co/T5RY5FKNvL",
        links=None,
        has_media=True,
    )

    assert result.display_text == "Crazy how Nvidia GPUs went to the moon."
    assert result.inline_tweet_links == []
    assert result.external_links == []


def test_normalize_tweet_links_keeps_expanded_external_and_drops_unresolved_self_for_media(monkeypatch):
    mapping = {
        "https://t.co/ext": "https://github.com/aliasvault/aliasvault",
        "https://t.co/self": "https://t.co/self",
    }
    monkeypatch.setattr("twag.link_utils._expand_short_url", lambda url: mapping.get(url, url))

    result = normalize_tweet_links(
        tweet_id="2019486959219913208",
        text="Password manager with email aliasing and built-in server\n\nhttps://t.co/ext https://t.co/self",
        links=None,
        has_media=True,
    )

    assert result.display_text == (
        "Password manager with email aliasing and built-in server\nhttps://github.com/aliasvault/aliasvault"
    )
    assert result.inline_tweet_links == []
    assert result.external_links == [
        {
            "url": "https://github.com/aliasvault/aliasvault",
            "display_url": "github.com/aliasvault/aliasvault",
            "domain": "github.com",
        }
    ]


def test_normalize_tweet_links_drops_only_trailing_unresolved_short_link_for_media(monkeypatch):
    monkeypatch.setattr("twag.link_utils._expand_short_url", lambda url: url)

    result = normalize_tweet_links(
        tweet_id="2018897246536818821",
        text="LLM for voice interactions without ASR stage\n\nhttps://t.co/JBlilG6yJ3 https://t.co/EydDPvMxiS",
        links=None,
        has_media=True,
    )

    assert result.display_text == "LLM for voice interactions without ASR stage\nhttps://t.co/JBlilG6yJ3"
    assert result.inline_tweet_links == []
    assert result.external_links == [
        {
            "url": "https://t.co/JBlilG6yJ3",
            "display_url": "t.co/JBlilG6yJ3",
            "domain": "t.co",
        }
    ]


def test_normalize_tweet_links_drops_trailing_unresolved_short_link_when_other_link_resolved(monkeypatch):
    mapping = {
        "https://t.co/ext": "https://github.com/fixie-ai/ultravox",
        "https://t.co/self": "https://t.co/self",
    }
    monkeypatch.setattr("twag.link_utils._expand_short_url", lambda url: mapping.get(url, url))

    result = normalize_tweet_links(
        tweet_id="2018897246536818821",
        text="LLM for voice interactions without ASR stage\n\nhttps://t.co/ext https://t.co/self",
        links=None,
        has_media=False,
    )

    assert result.display_text == "LLM for voice interactions without ASR stage\nhttps://github.com/fixie-ai/ultravox"
    assert result.inline_tweet_links == []
    assert result.external_links == [
        {
            "url": "https://github.com/fixie-ai/ultravox",
            "display_url": "github.com/fixie-ai/ultravox",
            "domain": "github.com",
        }
    ]


def test_expand_links_in_place_limits_short_url_expansions(monkeypatch):
    seen: list[str] = []

    def _fake_expand(url: str) -> str:
        seen.append(url)
        return url.replace("https://t.co/", "https://expanded.example/")

    monkeypatch.setattr("twag.link_utils._expand_short_url", _fake_expand)

    expanded = expand_links_in_place(
        [
            {"url": "https://t.co/one"},
            {"url": "https://t.co/two"},
            {"url": "https://t.co/three"},
        ]
    )

    assert len(seen) == 2
    assert expanded[0]["expanded_url"] == "https://expanded.example/one"
    assert expanded[1]["expanded_url"] == "https://expanded.example/two"
    assert expanded[2]["expanded_url"] == "https://t.co/three"


def test_normalize_tweet_links_already_expanded_skips_network_expansion(monkeypatch):
    monkeypatch.setattr(
        "twag.link_utils._expand_short_url",
        lambda _url: (_ for _ in ()).throw(AssertionError("_expand_short_url should not be called")),
    )

    result = normalize_tweet_links(
        tweet_id="123",
        text="Check this out https://t.co/ext",
        links=[
            {
                "url": "https://t.co/ext",
                "expanded_url": "https://example.com/report",
                "display_url": "example.com/report",
            }
        ],
        already_expanded=True,
    )

    assert result.display_text == "Check this out https://example.com/report"
    assert result.external_links == [
        {
            "url": "https://example.com/report",
            "display_url": "example.com/report",
            "domain": "example.com",
        }
    ]


# --- Tests for parse_tweet_status_id ---


def test_parse_tweet_status_id_x_url():
    assert parse_tweet_status_id("https://x.com/user/status/12345") == "12345"


def test_parse_tweet_status_id_twitter_url():
    assert parse_tweet_status_id("https://twitter.com/user/status/67890") == "67890"


def test_parse_tweet_status_id_mobile_url():
    assert parse_tweet_status_id("https://mobile.x.com/user/status/11111") == "11111"


def test_parse_tweet_status_id_with_query_params():
    assert parse_tweet_status_id("https://x.com/user/status/12345?s=20") == "12345"


def test_parse_tweet_status_id_none():
    assert parse_tweet_status_id(None) is None


def test_parse_tweet_status_id_non_tweet_url():
    assert parse_tweet_status_id("https://example.com/page") is None


def test_parse_tweet_status_id_empty_string():
    assert parse_tweet_status_id("") is None


# --- Tests for extract_urls_from_text ---


def test_extract_urls_from_text_multiple():
    text = "Visit https://example.com and http://other.org/page"
    urls = extract_urls_from_text(text)
    assert "https://example.com" in urls
    assert "http://other.org/page" in urls


def test_extract_urls_from_text_none():
    assert extract_urls_from_text(None) == []


def test_extract_urls_from_text_empty():
    assert extract_urls_from_text("") == []


def test_extract_urls_from_text_no_urls():
    assert extract_urls_from_text("no links here") == []


def test_extract_urls_from_text_deduplicates():
    text = "https://example.com and again https://example.com"
    urls = extract_urls_from_text(text)
    assert len(urls) == 1


# --- Tests for remove_urls_from_text ---


def test_remove_urls_from_text_removes_matching():
    text = "before https://example.com after"
    result = remove_urls_from_text(text, {"https://example.com"})
    assert "https://example.com" not in result
    assert "before" in result
    assert "after" in result


def test_remove_urls_from_text_empty_set():
    text = "keep https://example.com"
    assert remove_urls_from_text(text, set()) == text


def test_remove_urls_from_text_empty_text():
    assert remove_urls_from_text("", {"https://example.com"}) == ""


# --- Tests for clean_url_candidate ---


def test_clean_url_candidate_trailing_punctuation():
    assert clean_url_candidate("https://example.com).") == "https://example.com"


def test_clean_url_candidate_clean():
    assert clean_url_candidate("https://example.com/path") == "https://example.com/path"


def test_clean_url_candidate_whitespace():
    assert clean_url_candidate("  https://example.com  ") == "https://example.com"
