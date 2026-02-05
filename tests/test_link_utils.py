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
        "Password manager with email aliasing and built-in server\n"
        "https://github.com/aliasvault/aliasvault"
    )
    assert result.inline_tweet_links == []
    assert result.external_links == [
        {
            "url": "https://github.com/aliasvault/aliasvault",
            "display_url": "github.com/aliasvault/aliasvault",
            "domain": "github.com",
        }
    ]
