"""Telegram alert messages must HTML-escape attacker-controlled tweet text.

format_alert builds messages that send_telegram_alert posts with
parse_mode=HTML; without escaping, a tweet containing <script> or <b> tags
would be interpreted as Telegram-side HTML.
"""

from twag.notifier import format_alert


def test_format_alert_escapes_html_tags_in_content():
    msg = format_alert(
        tweet_id="123",
        author_handle="trader",
        content="<script>alert(1)</script><b>bold</b>",
        category="macro",
        summary="",
    )
    assert "<script>" not in msg
    assert "</script>" not in msg
    assert "<b>" not in msg
    assert "&lt;script&gt;" in msg
    assert "&lt;b&gt;bold&lt;/b&gt;" in msg


def test_format_alert_escapes_html_in_summary():
    msg = format_alert(
        tweet_id="123",
        author_handle="trader",
        content="benign",
        category="macro",
        summary="<i>injected</i>",
    )
    assert "<i>injected</i>" not in msg
    assert "&lt;i&gt;injected&lt;/i&gt;" in msg


def test_format_alert_escapes_html_in_author_handle():
    msg = format_alert(
        tweet_id="123",
        author_handle="<b>evil</b>",
        content="benign",
        category="macro",
        summary="",
    )
    assert "<b>evil</b>" not in msg
    assert "&lt;b&gt;evil&lt;/b&gt;" in msg


def test_format_alert_escapes_html_in_tickers():
    msg = format_alert(
        tweet_id="123",
        author_handle="trader",
        content="benign",
        category="macro",
        summary="",
        tickers=["<script>x</script>"],
    )
    assert "<script>x</script>" not in msg
    assert "&lt;script&gt;x&lt;/script&gt;" in msg


def test_format_alert_escapes_ampersand_in_content():
    msg = format_alert(
        tweet_id="123",
        author_handle="trader",
        content="A & B",
        category="macro",
        summary="",
    )
    # raw '&' would break HTML parse mode; must be entity-encoded
    assert "A &amp; B" in msg
