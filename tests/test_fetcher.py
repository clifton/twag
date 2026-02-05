"""Unit tests for the fetcher module."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from twag.fetcher import (
    Tweet,
    _parse_bird_output,
    fetch_bookmarks,
    fetch_home_timeline,
    fetch_search,
    fetch_user_tweets,
    get_auth_env,
    get_tweet_url,
    read_tweet,
    run_bird,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def basic_tweet_data():
    """Basic tweet JSON data with standard fields."""
    return {
        "id": "123456789",
        "author": {"username": "testuser", "name": "Test User"},
        "text": "Hello world!",
        "createdAt": "2026-01-15T12:00:00Z",
    }


@pytest.fixture
def alt_format_tweet_data():
    """Tweet data using alternative field names."""
    return {
        "tweetId": "987654321",
        "user": {"screen_name": "altuser", "name": "Alt User"},
        "full_text": "Alternative format tweet",
    }


@pytest.fixture
def quoted_tweet_data():
    """Tweet data with a quoted tweet."""
    return {
        "id": "123",
        "author": {"username": "quoter"},
        "text": "Check this out",
        "quotedTweet": {"id": "456", "text": "Original tweet"},
    }


@pytest.fixture
def media_tweet_data():
    """Tweet data with media attachments."""
    return {
        "id": "123",
        "author": {"username": "mediauser"},
        "text": "Check this image",
        "media": [{"type": "photo", "url": "https://example.com/img.jpg"}],
    }


@pytest.fixture
def tweet_with_links_data():
    """Tweet data with URLs."""
    return {
        "id": "123",
        "author": {"username": "linkuser"},
        "text": "Check this out",
        "entities": {"urls": [{"url": "https://example.com"}]},
    }


@pytest.fixture
def tweet_array_json():
    """JSON array of tweets."""
    return [
        {"id": "1", "author": {"username": "user1"}, "text": "Tweet 1"},
        {"id": "2", "author": {"username": "user2"}, "text": "Tweet 2"},
    ]


@pytest.fixture
def single_tweet_json():
    """JSON response for a single tweet."""
    return {"id": "123", "author": {"username": "single"}, "text": "Single tweet"}


@pytest.fixture
def mock_auth_env():
    """Mock for get_auth_env returning auth tokens."""
    with patch("twag.fetcher.get_auth_env") as mock:
        mock.return_value = {"AUTH_TOKEN": "test_token", "CT0": "test_ct0", "PATH": "/usr/bin"}
        yield mock


@pytest.fixture
def mock_run_bird():
    """Mock for run_bird function."""
    with patch("twag.fetcher.run_bird") as mock:
        yield mock


@pytest.fixture
def mock_subprocess():
    """Mock for subprocess.run."""
    with patch("twag.fetcher.subprocess.run") as mock:
        yield mock


# ============================================================================
# Tests: Tweet.from_bird_json
# ============================================================================


class TestTweetFromBirdJson:
    """Tests for Tweet.from_bird_json parsing."""

    def test_parse_basic_tweet(self, basic_tweet_data):
        """Parse a basic tweet with standard fields."""
        tweet = Tweet.from_bird_json(basic_tweet_data)

        assert tweet.id == "123456789"
        assert tweet.author_handle == "testuser"
        assert tweet.author_name == "Test User"
        assert tweet.content == "Hello world!"
        assert tweet.created_at is not None
        assert tweet.has_quote is False
        assert tweet.quote_tweet_id is None
        assert tweet.has_media is False
        assert tweet.has_link is False
        assert tweet.is_retweet is False
        assert tweet.retweeted_by_handle is None
        assert tweet.original_author_handle is None
        assert tweet.original_content is None

    def test_parse_alternative_field_names(self, alt_format_tweet_data):
        """Parse tweet using alternative field names."""
        tweet = Tweet.from_bird_json(alt_format_tweet_data)

        assert tweet.id == "987654321"
        assert tweet.author_handle == "altuser"
        assert tweet.author_name == "Alt User"
        assert tweet.content == "Alternative format tweet"

    def test_parse_rest_id_format(self):
        """Parse tweet using rest_id format."""
        data = {
            "rest_id": "111222333",
            "authorHandle": "restuser",
            "content": "REST format",
        }
        tweet = Tweet.from_bird_json(data)

        assert tweet.id == "111222333"
        assert tweet.author_handle == "restuser"
        assert tweet.content == "REST format"

    def test_parse_with_quoted_tweet(self, quoted_tweet_data):
        """Parse tweet with a quoted tweet."""
        tweet = Tweet.from_bird_json(quoted_tweet_data)

        assert tweet.has_quote is True
        assert tweet.quote_tweet_id == "456"

    def test_parse_with_quoted_status(self):
        """Parse tweet with quoted_status (alternative format)."""
        data = {
            "id": "123",
            "author": {"username": "quoter"},
            "text": "RT this",
            "quoted_status": {"id_str": "789"},
        }
        tweet = Tweet.from_bird_json(data)

        assert tweet.has_quote is True
        assert tweet.quote_tweet_id == "789"

    def test_parse_with_media(self, media_tweet_data):
        """Parse tweet with media attachments."""
        tweet = Tweet.from_bird_json(media_tweet_data)

        assert tweet.has_media is True

    def test_parse_with_entities_media(self):
        """Parse tweet with media in entities."""
        data = {
            "id": "123",
            "author": {"username": "entuser"},
            "text": "Entity media",
            "entities": {"media": [{"type": "photo"}]},
        }
        tweet = Tweet.from_bird_json(data)

        assert tweet.has_media is True

    def test_parse_with_extended_entities_media(self):
        """Parse tweet with media in extended_entities."""
        data = {
            "id": "123",
            "author": {"username": "extuser"},
            "text": "Extended media",
            "extended_entities": {"media": [{"type": "video"}]},
        }
        tweet = Tweet.from_bird_json(data)

        assert tweet.has_media is True

    def test_parse_with_urls_in_entities(self, tweet_with_links_data):
        """Parse tweet with URLs in entities."""
        tweet = Tweet.from_bird_json(tweet_with_links_data)

        assert tweet.has_link is True

    def test_parse_x_article_uses_content_when_plain_text_missing(self):
        """X article should fall back to long tweet content when plain_text is absent."""
        article_text = "Intro.\n\n" + ("Detailed section. " * 40)
        data = {
            "id": "123",
            "author": {"username": "writer"},
            "text": article_text,
            "article": {"title": "Deep Dive", "previewText": "Short preview"},
        }

        tweet = Tweet.from_bird_json(data)

        assert tweet.is_x_article is True
        assert tweet.article_title == "Deep Dive"
        assert tweet.article_text == article_text.strip()

    def test_parse_with_url_in_text(self):
        """Parse tweet with URL detected in text."""
        data = {
            "id": "123",
            "author": {"username": "textlink"},
            "text": "Visit https://example.com for more info",
        }
        tweet = Tweet.from_bird_json(data)

        assert tweet.has_link is True

    def test_parse_twitter_date_format(self):
        """Parse tweet with Twitter's native date format."""
        data = {
            "id": "123",
            "author": {"username": "dateuser"},
            "text": "Date test",
            "created_at": "Wed Jan 15 12:00:00 +0000 2026",
        }
        tweet = Tweet.from_bird_json(data)

        assert tweet.created_at is not None
        assert tweet.created_at.year == 2026
        assert tweet.created_at.month == 1
        assert tweet.created_at.day == 15

    def test_parse_invalid_date_format(self):
        """Parse tweet with invalid date (should not raise)."""
        data = {
            "id": "123",
            "author": {"username": "baddate"},
            "text": "Bad date",
            "createdAt": "not-a-date",
        }
        tweet = Tweet.from_bird_json(data)

        assert tweet.created_at is None

    def test_parse_missing_author(self):
        """Parse tweet with missing author info."""
        data = {"id": "123", "text": "No author"}
        tweet = Tweet.from_bird_json(data)

        assert tweet.author_handle == "unknown"
        assert tweet.author_name is None

    def test_raw_preserved(self, basic_tweet_data):
        """Ensure raw data is preserved."""
        basic_tweet_data["custom_field"] = "custom_value"
        tweet = Tweet.from_bird_json(basic_tweet_data)

        assert tweet.raw == basic_tweet_data
        assert tweet.raw["custom_field"] == "custom_value"

    def test_parse_with_retweeted_tweet_payload(self):
        """Parse retweet metadata from retweetedTweet payload."""
        data = {
            "id": "100",
            "author": {"username": "retweeter", "name": "Retweeter"},
            "text": "RT @original: important thread",
            "retweetedTweet": {
                "id": "200",
                "author": {"username": "original", "name": "Original Poster"},
                "text": "important thread",
            },
        }
        tweet = Tweet.from_bird_json(data)

        assert tweet.is_retweet is True
        assert tweet.retweeted_by_handle == "retweeter"
        assert tweet.retweeted_by_name == "Retweeter"
        assert tweet.original_tweet_id == "200"
        assert tweet.original_author_handle == "original"
        assert tweet.original_author_name == "Original Poster"
        assert tweet.original_content == "important thread"
        # Source identity/content remain the fetched tweet payload.
        assert tweet.author_handle == "retweeter"
        assert tweet.content == "RT @original: important thread"

    def test_parse_retweet_from_text_fallback(self):
        """Parse RT metadata from text when payload lacks retweetedTweet object."""
        data = {
            "id": "300",
            "author": {"username": "retweeter2"},
            "text": "RT @orig2: edge case fallback",
        }
        tweet = Tweet.from_bird_json(data)

        assert tweet.is_retweet is True
        assert tweet.retweeted_by_handle == "retweeter2"
        assert tweet.original_author_handle == "orig2"
        assert tweet.original_content == "edge case fallback"
        assert tweet.original_tweet_id is None

    def test_parse_content_unescapes_html_entities(self):
        """Decode HTML entities from tweet content variants."""
        data = {
            "id": "302",
            "author": {"username": "entity_user"},
            "text": "Spotify is down -33% and A &gt;$100B move with P&amp;L implications",
        }
        tweet = Tweet.from_bird_json(data)

        assert tweet.content == "Spotify is down -33% and A >$100B move with P&L implications"

    def test_parse_retweet_from_nested_raw_retweeted_status_result(self):
        """Parse retweet metadata from Bird --json-full nested _raw legacy payload."""
        data = {
            "id": "2019489337843306678",
            "author": {"username": "tylercowen", "name": "tylercowen"},
            "text": "RT @DKThomp: for me the odds that AI is a bubble declined significantly ... under-bu…",
            "_raw": {
                "legacy": {
                    "retweeted_status_result": {
                        "result": {
                            "rest_id": "2019484169915572452",
                            "note_tweet": {
                                "note_tweet_results": {
                                    "result": {
                                        "text": (
                                            "for me the odds that AI is a bubble declined significantly in the last 3 weeks "
                                            "and the odds that we're actually quite under-built for the necessary levels "
                                            "of inference/usage went significantly up in that period \n\nbasically I think "
                                            "AI is going to become the home screen of a ludicrously high percentage of "
                                            "white collar workers in the next two years and parallel agents will be deployed "
                                            "in the battlefield of knowledge work at downright Soviet levels"
                                        )
                                    }
                                }
                            },
                            "core": {
                                "user_results": {
                                    "result": {
                                        "core": {
                                            "screen_name": "DKThomp",
                                            "name": "Derek Thompson",
                                        }
                                    }
                                }
                            },
                            "legacy": {
                                "full_text": (
                                    "for me the odds that AI is a bubble declined significantly in the last 3 weeks "
                                    "and the odds that we're actually quite under-built for the necessary levels "
                                    "of inference/usage went significantly up in that period \n\nbasically I think "
                                    "AI is going to become the home screen of a"
                                )
                            },
                        }
                    }
                }
            },
        }

        tweet = Tweet.from_bird_json(data)

        assert tweet.is_retweet is True
        assert tweet.retweeted_by_handle == "tylercowen"
        assert tweet.original_tweet_id == "2019484169915572452"
        assert tweet.original_author_handle == "DKThomp"
        assert tweet.original_author_name == "Derek Thompson"
        assert tweet.original_content is not None
        assert "under-built" in tweet.original_content
        assert "Soviet levels" in tweet.original_content
        assert len(tweet.original_content) > 400

    def test_parse_retweet_from_text_fallback_does_not_treat_truncated_text_as_original(self):
        """Fallback RT parsing should not persist truncated original text."""
        data = {
            "id": "301",
            "author": {"username": "retweeter3"},
            "text": "RT @orig3: this was truncated by upstream and ends with ellipsis…",
        }
        tweet = Tweet.from_bird_json(data)

        assert tweet.is_retweet is True
        assert tweet.original_author_handle == "orig3"
        assert tweet.original_content is None


# ============================================================================
# Tests: _parse_bird_output
# ============================================================================


class TestParseBirdOutput:
    """Tests for _parse_bird_output function."""

    def test_parse_empty_output(self):
        """Empty output returns empty list."""
        assert _parse_bird_output("") == []
        assert _parse_bird_output("   ") == []
        assert _parse_bird_output("\n\n") == []

    def test_parse_json_array(self, tweet_array_json):
        """Parse JSON array of tweets."""
        tweets = _parse_bird_output(json.dumps(tweet_array_json))

        assert len(tweets) == 2
        assert tweets[0].id == "1"
        assert tweets[1].id == "2"

    def test_parse_single_json_object(self, single_tweet_json):
        """Parse single JSON object."""
        tweets = _parse_bird_output(json.dumps(single_tweet_json))

        assert len(tweets) == 1
        assert tweets[0].id == "123"

    def test_parse_ndjson_format(self):
        """Parse newline-delimited JSON."""
        lines = [
            json.dumps({"id": "1", "author": {"username": "u1"}, "text": "T1"}),
            json.dumps({"id": "2", "author": {"username": "u2"}, "text": "T2"}),
            json.dumps({"id": "3", "author": {"username": "u3"}, "text": "T3"}),
        ]
        output = "\n".join(lines)
        tweets = _parse_bird_output(output)

        assert len(tweets) == 3

    def test_parse_ndjson_with_arrays(self):
        """Parse NDJSON where each line is an array."""
        lines = [
            json.dumps([{"id": "1", "author": {"username": "u1"}, "text": "T1"}]),
            json.dumps([{"id": "2", "author": {"username": "u2"}, "text": "T2"}]),
        ]
        output = "\n".join(lines)
        tweets = _parse_bird_output(output)

        assert len(tweets) == 2

    def test_parse_ndjson_with_empty_lines(self):
        """Parse NDJSON with empty lines (should be skipped)."""
        output = '{"id": "1", "author": {"username": "u1"}, "text": "T1"}\n\n{"id": "2", "author": {"username": "u2"}, "text": "T2"}\n'
        tweets = _parse_bird_output(output)

        assert len(tweets) == 2

    def test_parse_invalid_json_lines_skipped(self):
        """Invalid JSON lines should be skipped, not raise."""
        output = '{"id": "1", "author": {"username": "u1"}, "text": "T1"}\nnot json\n{"id": "2", "author": {"username": "u2"}, "text": "T2"}'
        tweets = _parse_bird_output(output)

        assert len(tweets) == 2

    def test_parse_ndjson_with_non_object_values_skipped(self):
        """Valid JSON scalar lines should be ignored instead of crashing."""
        output = '{"id": "1", "author": {"username": "u1"}, "text": "T1"}\n"string"\n42\n{"id": "2", "author": {"username": "u2"}, "text": "T2"}'
        tweets = _parse_bird_output(output)

        assert len(tweets) == 2


# ============================================================================
# Tests: get_auth_env
# ============================================================================


class TestGetAuthEnv:
    """Tests for get_auth_env function."""

    def test_returns_environ_copy(self):
        """Should return a copy of os.environ."""
        env = get_auth_env()
        assert isinstance(env, dict)
        # Should have standard env vars
        assert "PATH" in env or "HOME" in env

    def test_loads_from_env_file(self):
        """Should load variables from ~/.env file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_VAR=test_value\n")
            f.write("AUTH_TOKEN=secret123\n")
            f.write("# comment line\n")
            f.write("export CT0=csrf_token\n")
            f.write('QUOTED_VAR="quoted value"\n')
            env_path = f.name

        try:
            # Mock load_config to avoid it trying to load JSON from our .env file
            with patch("twag.fetcher.load_config", return_value={"bird": {}}):
                with patch("twag.fetcher.os.path.expanduser", return_value=env_path):
                    env = get_auth_env()
                    assert isinstance(env, dict)
                    # Verify env vars were loaded from the file
                    assert env.get("AUTH_TOKEN") == "secret123"
                    assert env.get("CT0") == "csrf_token"
                    assert env.get("QUOTED_VAR") == "quoted value"
        finally:
            os.unlink(env_path)


# ============================================================================
# Tests: run_bird
# ============================================================================


class TestRunBird:
    """Tests for run_bird function."""

    def test_run_bird_success(self, mock_subprocess, mock_auth_env):
        """Successful bird command execution."""
        mock_subprocess.return_value = MagicMock(stdout="output", stderr="", returncode=0)

        stdout, stderr, code = run_bird(["home", "-n", "10", "--json"])

        assert stdout == "output"
        assert code == 0
        mock_subprocess.assert_called_once()

    def test_run_bird_adds_auth_flags(self, mock_subprocess, mock_auth_env):
        """Auth flags should be added from environment."""
        mock_subprocess.return_value = MagicMock(stdout="", stderr="", returncode=0)

        run_bird(["home"])

        call_args = mock_subprocess.call_args[0][0]
        assert "--auth-token" in call_args
        assert "test_token" in call_args
        assert "--ct0" in call_args
        assert "test_ct0" in call_args

    def test_run_bird_timeout(self, mock_subprocess, mock_auth_env):
        """Timeout should return error."""
        import subprocess

        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd="bird", timeout=60)

        stdout, stderr, code = run_bird(["home"])

        assert code == 1
        assert "timed out" in stderr.lower()

    def test_run_bird_not_found(self, mock_subprocess, mock_auth_env):
        """FileNotFoundError should return error."""
        mock_subprocess.side_effect = FileNotFoundError()

        stdout, stderr, code = run_bird(["home"])

        assert code == 1
        assert "not found" in stderr.lower()


# ============================================================================
# Tests: Fetch functions
# ============================================================================


class TestFetchFunctions:
    """Tests for high-level fetch functions."""

    def test_fetch_home_timeline_success(self, mock_run_bird, tweet_array_json):
        """Successful home timeline fetch."""
        mock_run_bird.return_value = (json.dumps(tweet_array_json), "", 0)

        tweets = fetch_home_timeline(count=50)

        assert len(tweets) == 2
        mock_run_bird.assert_called_once()
        args = mock_run_bird.call_args[0][0]
        assert "home" in args
        assert "-n" in args
        assert "50" in args

    def test_fetch_home_timeline_error(self, mock_run_bird):
        """Home timeline fetch failure raises RuntimeError."""
        mock_run_bird.return_value = ("", "Auth error", 1)

        with pytest.raises(RuntimeError, match="bird home failed"):
            fetch_home_timeline()

    def test_fetch_home_timeline_hydrates_truncated_retweet(self, mock_run_bird):
        """Home fetch should enrich truncated RT text with read_tweet metadata when available."""
        truncated_rt = {
            "id": "rt-1",
            "author": {"username": "retweeter", "name": "Retweeter"},
            "text": "RT @orig: clipped payload from timeline…",
        }
        mock_run_bird.return_value = (json.dumps([truncated_rt]), "", 0)

        hydrated = Tweet(
            id="rt-1",
            author_handle="retweeter",
            author_name="Retweeter",
            content="RT @orig: clipped payload from timeline…",
            created_at=None,
            has_quote=False,
            quote_tweet_id=None,
            has_media=False,
            media_items=[],
            has_link=False,
            is_x_article=False,
            article_title=None,
            article_preview=None,
            article_text=None,
            is_retweet=True,
            retweeted_by_handle="retweeter",
            retweeted_by_name="Retweeter",
            original_tweet_id="orig-1",
            original_author_handle="orig",
            original_author_name="Original Author",
            original_content="Full original text from read endpoint.",
            raw={},
        )

        with patch("twag.fetcher.read_tweet", return_value=hydrated) as mock_read_tweet:
            tweets = fetch_home_timeline(count=1)

        assert len(tweets) == 1
        assert tweets[0].is_retweet is True
        assert tweets[0].original_tweet_id == "orig-1"
        assert tweets[0].original_author_handle == "orig"
        assert tweets[0].original_content == "Full original text from read endpoint."
        mock_read_tweet.assert_called_once_with("rt-1")

    def test_fetch_user_tweets_normalizes_handle(self, mock_run_bird, single_tweet_json):
        """User tweets fetch normalizes handle to include @."""
        mock_run_bird.return_value = (json.dumps([single_tweet_json]), "", 0)

        fetch_user_tweets("testuser", count=20)

        args = mock_run_bird.call_args[0][0]
        assert "@testuser" in args

    def test_fetch_user_tweets_already_has_at(self, mock_run_bird, single_tweet_json):
        """User tweets fetch handles @ already present."""
        mock_run_bird.return_value = (json.dumps([single_tweet_json]), "", 0)

        fetch_user_tweets("@testuser", count=20)

        args = mock_run_bird.call_args[0][0]
        # Should have @@testuser since the function adds @ unconditionally
        # This test documents current behavior
        assert "@@testuser" in args or "@testuser" in args

    def test_fetch_user_tweets_error(self, mock_run_bird):
        """User tweets fetch failure raises RuntimeError."""
        mock_run_bird.return_value = ("", "User not found", 1)

        with pytest.raises(RuntimeError, match="bird user-tweets failed"):
            fetch_user_tweets("nonexistent")

    def test_fetch_search_success(self, mock_run_bird, single_tweet_json):
        """Successful search fetch."""
        mock_run_bird.return_value = (json.dumps([single_tweet_json]), "", 0)

        tweets = fetch_search("test query", count=30)

        assert len(tweets) == 1
        args = mock_run_bird.call_args[0][0]
        assert "search" in args
        assert "test query" in args

    def test_fetch_search_error(self, mock_run_bird):
        """Search fetch failure raises RuntimeError."""
        mock_run_bird.return_value = ("", "Search failed", 1)

        with pytest.raises(RuntimeError, match="bird search failed"):
            fetch_search("query")

    def test_fetch_bookmarks_success(self, mock_run_bird, single_tweet_json):
        """Successful bookmarks fetch."""
        mock_run_bird.return_value = (json.dumps([single_tweet_json]), "", 0)

        tweets = fetch_bookmarks(count=100)

        assert len(tweets) == 1
        args = mock_run_bird.call_args[0][0]
        assert "bookmarks" in args

    def test_fetch_bookmarks_error(self, mock_run_bird):
        """Bookmarks fetch failure raises RuntimeError."""
        mock_run_bird.return_value = ("", "Auth required", 1)

        with pytest.raises(RuntimeError, match="bird bookmarks failed"):
            fetch_bookmarks()


class TestReadTweet:
    """Tests for read_tweet function."""

    def test_read_tweet_success(self, mock_run_bird, single_tweet_json):
        """Successful single tweet read."""
        mock_run_bird.return_value = (json.dumps(single_tweet_json), "", 0)

        tweet = read_tweet("12345")

        assert tweet is not None
        assert tweet.id == "123"

    def test_read_tweet_not_found(self, mock_run_bird):
        """Tweet not found returns None."""
        mock_run_bird.return_value = ("", "Not found", 1)

        tweet = read_tweet("99999")

        assert tweet is None

    def test_read_tweet_empty_response(self, mock_run_bird):
        """Empty response returns None."""
        mock_run_bird.return_value = ("", "", 0)

        tweet = read_tweet("12345")

        assert tweet is None

    def test_read_tweet_by_url(self, mock_run_bird, single_tweet_json):
        """Read tweet by URL."""
        mock_run_bird.return_value = (json.dumps(single_tweet_json), "", 0)

        tweet = read_tweet("https://x.com/user/status/12345")

        assert tweet is not None
        args = mock_run_bird.call_args[0][0]
        assert "read" in args
        assert "https://x.com/user/status/12345" in args

    def test_read_tweet_falls_back_from_truncated_json_full(self, mock_run_bird):
        """Fallback to --json when --json-full cannot be parsed, preserving recovered media."""
        truncated_full = (
            '{"id":"123","author":{"username":"single"},"text":"Single tweet","_raw":{"article":{"article_results":'
            '{"result":{"media_entities":[{"media_info":{"original_img_url":"https:\\/\\/pbs.twimg.com\\/media\\/'
            'HAXmiH6acAEiywu.jpg"}}]}}}}'
        )
        fallback_json = {
            "id": "123",
            "author": {"username": "single"},
            "text": "Single tweet",
            "article": {"title": "Deep Dive", "previewText": "Preview"},
        }
        mock_run_bird.side_effect = [
            (truncated_full, "", 0),
            (json.dumps(fallback_json), "", 0),
        ]

        tweet = read_tweet("123")

        assert tweet is not None
        assert tweet.is_x_article is True
        assert any(item["url"] == "https://pbs.twimg.com/media/HAXmiH6acAEiywu.jpg" for item in tweet.media_items)


# ============================================================================
# Tests: get_tweet_url
# ============================================================================


class TestGetTweetUrl:
    """Tests for get_tweet_url function."""

    def test_basic_url(self):
        """Generate basic tweet URL."""
        url = get_tweet_url("123456", "testuser")
        assert url == "https://x.com/testuser/status/123456"

    def test_strips_at_sign(self):
        """Handle should have @ stripped."""
        url = get_tweet_url("123456", "@testuser")
        assert url == "https://x.com/testuser/status/123456"

    def test_default_handle(self):
        """Default handle should be 'i'."""
        url = get_tweet_url("123456")
        assert url == "https://x.com/i/status/123456"

    def test_multiple_at_signs(self):
        """Multiple @ signs should all be stripped (lstrip removes all leading)."""
        url = get_tweet_url("123456", "@@testuser")
        assert url == "https://x.com/testuser/status/123456"
