"""Tests for digest link normalization and linked tweet rendering."""

from datetime import datetime, timezone

from twag.db import get_connection, init_db, insert_tweet, update_tweet_processing
from twag.renderer import render_digest


def test_render_digest_removes_self_links_and_renders_external_and_inline(monkeypatch, tmp_path):
    db_path = tmp_path / "twag_renderer_links.db"
    init_db(db_path)

    now = datetime.now(timezone.utc)
    digest_date = now.strftime("%Y-%m-%d")

    with get_connection(db_path) as conn:
        # Linked tweet is present in DB but intentionally not processed for digest inclusion.
        inserted = insert_tweet(
            conn,
            tweet_id="2001",
            author_handle="child_user",
            content="child linked content",
            created_at=now,
            source="test",
        )
        assert inserted is True

        inserted = insert_tweet(
            conn,
            tweet_id="1001",
            author_handle="root_user",
            content="Interesting thread https://t.co/self https://t.co/child https://t.co/ext",
            created_at=now,
            source="test",
            has_link=True,
            links=[
                {
                    "url": "https://t.co/self",
                    "expanded_url": "https://x.com/root_user/status/1001",
                    "display_url": "x.com/root_user/status/1001",
                },
                {
                    "url": "https://t.co/child",
                    "expanded_url": "https://x.com/child_user/status/2001",
                    "display_url": "x.com/child_user/status/2001",
                },
                {
                    "url": "https://t.co/ext",
                    "expanded_url": "https://github.com/aliasvault/aliasvault",
                    "display_url": "github.com/aliasvault/aliasvault",
                },
            ],
        )
        assert inserted is True
        update_tweet_processing(
            conn,
            tweet_id="1001",
            relevance_score=8.0,
            categories=["tech_business"],
            summary="Root summary",
            signal_tier="high_signal",
            tickers=["GTLB"],
        )
        conn.commit()

    monkeypatch.setattr("twag.renderer.get_connection", lambda: get_connection(db_path))
    output_path = tmp_path / "digest.md"
    content = render_digest(date=digest_date, min_score=5.0, output_path=output_path)

    assert "https://t.co/self" not in content
    assert "https://t.co/child" not in content
    assert "https://t.co/ext" not in content
    assert "Interesting thread" in content
    assert "🌐 **Links:**" in content
    assert "[github.com/aliasvault/aliasvault](https://github.com/aliasvault/aliasvault)" in content
    assert "💬 **Linked Tweets:**" in content
    assert "**@child_user**: child linked content" in content


def test_render_digest_does_not_expand_short_urls_at_render_time(monkeypatch, tmp_path):
    db_path = tmp_path / "twag_renderer_no_runtime_expansion.db"
    init_db(db_path)

    now = datetime.now(timezone.utc)
    digest_date = now.strftime("%Y-%m-%d")

    with get_connection(db_path) as conn:
        inserted = insert_tweet(
            conn,
            tweet_id="3001",
            author_handle="root_user",
            content="Interesting link https://t.co/ext",
            created_at=now,
            source="test",
            has_link=True,
            links=[
                {
                    "url": "https://t.co/ext",
                    "expanded_url": "https://github.com/example/project",
                    "display_url": "github.com/example/project",
                }
            ],
        )
        assert inserted is True
        update_tweet_processing(
            conn,
            tweet_id="3001",
            relevance_score=8.0,
            categories=["tech_business"],
            summary="Root summary",
            signal_tier="high_signal",
            tickers=["GTLB"],
        )
        conn.commit()

    monkeypatch.setattr("twag.link_utils._expand_short_url", lambda _url: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr("twag.renderer.get_connection", lambda: get_connection(db_path))

    output_path = tmp_path / "digest.md"
    content = render_digest(date=digest_date, min_score=5.0, output_path=output_path)

    assert "https://github.com/example/project" in content
