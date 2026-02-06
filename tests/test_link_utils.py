from twag.link_utils import normalize_tweet_links


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
