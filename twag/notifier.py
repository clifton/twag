"""Telegram notifications for high-signal tweets."""

import os
from datetime import datetime

import httpx

from .config import load_config
from .fetcher import get_tweet_url


def is_quiet_hours() -> bool:
    """Check if we're in quiet hours (no notifications)."""
    config = load_config()
    notif_config = config.get("notifications", {})

    start = notif_config.get("quiet_hours_start", 23)
    end = notif_config.get("quiet_hours_end", 8)

    now = datetime.now()
    hour = now.hour

    # Handle overnight quiet hours (e.g., 23:00 to 08:00)
    if start > end:
        return hour >= start or hour < end
    else:
        return start <= hour < end


def get_recent_alert_count() -> int:
    """Get count of alerts sent in the last hour."""
    # TODO: Track in database
    # For now, return 0 to allow alerts
    return 0


def can_send_alert(score: float = 0) -> bool:
    """Check if we can send an alert now."""
    config = load_config()
    notif_config = config.get("notifications", {})

    # Check if enabled
    if not notif_config.get("telegram_enabled", True):
        return False

    # Score 10 overrides quiet hours
    if score >= 10:
        return True

    # Check quiet hours
    if is_quiet_hours():
        return False

    # Check rate limit
    max_per_hour = notif_config.get("max_alerts_per_hour", 10)
    if get_recent_alert_count() >= max_per_hour:
        return False

    return True


def format_alert(
    tweet_id: str,
    author_handle: str,
    content: str,
    category: str | list[str],
    summary: str,
    tickers: list[str] | None = None,
) -> str:
    """Format a high-signal alert message."""
    # Truncate content for preview
    preview = content[:150] + "..." if len(content) > 150 else content

    # Category display - handle list or string
    if isinstance(category, list):
        cats = [c for c in category if c != "noise"]
        cat_display = ", ".join(c.replace("_", " ").upper() for c in cats) if cats else "MARKET"
    else:
        cat_display = category.replace("_", " ").upper() if category else "MARKET"

    # Build message
    lines = [
        f"🚨 HIGH SIGNAL [{cat_display}]",
        f'@{author_handle}: "{preview}"',
        "",
    ]

    if summary:
        lines.append(f"📊 {summary}")

    if tickers:
        lines.append(f"💡 Tickers: {', '.join(tickers)}")

    url = get_tweet_url(tweet_id, author_handle)
    lines.append(f"🔗 {url}")

    return "\n".join(lines)


def send_telegram_alert(
    message: str,
    chat_id: str | None = None,
) -> bool:
    """Send a Telegram alert. Returns True if successful."""
    config = load_config()
    notif_config = config.get("notifications", {})

    # Get chat ID
    if chat_id is None:
        chat_id = notif_config.get("telegram_chat_id")
        if not chat_id:
            chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not chat_id:
        return False

    # Get bot token
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return False

    # Send via Telegram API
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    try:
        response = httpx.post(
            url,
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=10,
        )
        return response.status_code == 200
    except Exception:
        return False


def notify_high_signal_tweet(
    tweet_id: str,
    author_handle: str,
    content: str,
    score: float,
    category: str | list[str],
    summary: str,
    tickers: list[str] | None = None,
) -> bool:
    """Send notification for a high-signal tweet."""
    config = load_config()
    alert_threshold = config["scoring"]["alert_threshold"]

    # Check if score meets threshold
    if score < alert_threshold:
        return False

    # Check if we can send
    if not can_send_alert(score):
        return False

    # Format and send
    message = format_alert(
        tweet_id=tweet_id,
        author_handle=author_handle,
        content=content,
        category=category,
        summary=summary,
        tickers=tickers,
    )

    return send_telegram_alert(message)
