"""Bird CLI wrapper for fetching tweets."""

from .bird_cli import (
    UserNotFoundError,
    _parse_bird_output,
    fetch_bookmarks,
    fetch_home_timeline,
    fetch_replies,
    fetch_search,
    fetch_thread,
    fetch_user_tweets,
    get_auth_env,
    get_tweet_url,
    read_tweet,
    run_bird,
)
from .extractors import Tweet

__all__ = [
    "Tweet",
    "UserNotFoundError",
    "_parse_bird_output",
    "fetch_bookmarks",
    "fetch_home_timeline",
    "fetch_replies",
    "fetch_search",
    "fetch_thread",
    "fetch_user_tweets",
    "get_auth_env",
    "get_tweet_url",
    "read_tweet",
    "run_bird",
]
