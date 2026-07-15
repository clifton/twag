"""Integration coverage for analyze thread/reply context persistence."""

import json

import twag.processor.storage as storage_mod
from twag.db import get_connection, get_tweet_by_id, init_db
from twag.fetcher import Tweet


def _tweet(
    tweet_id: str,
    *,
    parent_id: str | None = None,
    article: bool = False,
) -> Tweet:
    return Tweet(
        id=tweet_id,
        author_handle=f"user_{tweet_id}",
        author_name=f"User {tweet_id}",
        content=f"Status {tweet_id} https://example.com/{tweet_id}",
        created_at=None,
        has_quote=False,
        quote_tweet_id=None,
        in_reply_to_tweet_id=parent_id,
        conversation_id="target",
        has_media=True,
        media_items=[{"type": "photo", "url": f"https://pbs.twimg.com/{tweet_id}.jpg"}],
        has_link=True,
        is_x_article=article,
        article_title="Target article" if article else None,
        article_preview="Target preview" if article else None,
        article_text="Target article body" if article else None,
        is_retweet=False,
        retweeted_by_handle=None,
        retweeted_by_name=None,
        original_tweet_id=None,
        original_author_handle=None,
        original_author_name=None,
        original_content=None,
        raw={},
        links=[
            {
                "url": f"https://t.co/{tweet_id}",
                "expanded_url": f"https://example.com/{tweet_id}",
                "display_url": f"example.com/{tweet_id}",
            },
        ],
    )


def test_context_storage_preserves_relationships_and_rich_metadata(monkeypatch, tmp_path):
    """Analyze context uses normal storage, including extraction-critical fields."""
    db_path = tmp_path / "analyze-context.db"
    init_db(db_path)
    monkeypatch.setattr(storage_mod, "get_connection", lambda: get_connection(db_path))
    monkeypatch.setattr(storage_mod, "load_config", lambda: {"fetch": {"quote_depth": 0, "quote_delay": 0}})

    target = _tweet("target", article=True)
    reply = _tweet("reply", parent_id="target")
    fetched, new = storage_mod.store_fetched_tweets(
        [target, reply],
        source="status",
        query_params={
            "thread": True,
            "replies": True,
            "reply_depth": 2,
            "max_reply_nodes": 25,
            "max_pages": 5,
        },
    )

    assert (fetched, new) == (2, 2)
    with get_connection(db_path) as conn:
        target_row = get_tweet_by_id(conn, "target")
        reply_row = get_tweet_by_id(conn, "reply")
        fetch_row = conn.execute("SELECT endpoint, query_params FROM fetch_log ORDER BY id DESC LIMIT 1").fetchone()

    assert target_row is not None
    assert target_row["is_x_article"] == 1
    assert target_row["article_title"] == "Target article"
    assert target_row["article_preview"] == "Target preview"
    assert target_row["article_text"] == "Target article body"
    assert json.loads(target_row["media_items"])[0]["url"].endswith("target.jpg")
    assert json.loads(target_row["links_json"])[0]["expanded_url"].endswith("/target")

    assert reply_row is not None
    assert reply_row["in_reply_to_tweet_id"] == "target"
    assert reply_row["conversation_id"] == "target"
    assert reply_row["source"] == "status"
    assert fetch_row["endpoint"] == "status"
    assert json.loads(fetch_row["query_params"])["max_pages"] == 5
