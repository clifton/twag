"""Telegram notifications for high-signal tweets."""

import logging
import os
import shutil
import subprocess
from datetime import datetime

import httpx

from .config import load_config
from .db import get_connection, log_alert
from .db import get_recent_alert_count as _db_get_recent_alert_count
from .fetcher import get_tweet_url
from .registry import match_positions

log = logging.getLogger(__name__)


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
    return start <= hour < end


def get_recent_alert_count() -> int:
    """Get count of alerts sent in the last hour from the database."""
    try:
        with get_connection() as conn:
            return _db_get_recent_alert_count(conn, minutes=60)
    except Exception:
        log.warning("Failed to query alert log; allowing alert")
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
    surprise: int = 0,
    playbook_trigger: str | None = None,
    catalyst_status: str | None = None,
    themes: list[str] | None = None,
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

    if catalyst_status == "resolved":
        header = "⚠️ RESOLVED"
    elif playbook_trigger:
        header = f"🚨 PLAYBOOK: {playbook_trigger.upper()}"
    elif surprise == 2:
        header = "🚨 SURPRISE"
    else:
        header = "🚨 HIGH SIGNAL"

    lines = [
        f"{header} [{cat_display}]",
        f'@{author_handle}: "{preview}"',
    ]

    if summary:
        lines.append(f"📊 {summary}")

    position_match = match_positions(themes, tickers)
    if position_match:
        lines.append(f"🎯 {position_match}")
    elif tickers:
        lines.append(f"💡 Tickers: {', '.join(tickers)}")

    url = get_tweet_url(tweet_id, author_handle)
    lines.append(f"🔗 {url}")

    return "\n".join(lines)


def should_alert(
    score: float,
    surprise: int = 0,
    playbook_trigger: str | None = None,
    catalyst_status: str | None = None,
    *,
    alert_threshold: float | None = None,
) -> bool:
    """Return whether a scored tweet meets any real-time alert trigger."""
    threshold = alert_threshold
    if threshold is None:
        threshold = float(load_config()["scoring"]["alert_threshold"])
    return bool(
        score >= threshold
        or (surprise == 2 and score >= 7)
        or (playbook_trigger and score >= 6)
        or (catalyst_status == "resolved" and score >= 6),
    )


def _resolve_chat_id(chat_id: str | None = None) -> str | None:
    if chat_id:
        return chat_id
    configured = load_config().get("notifications", {}).get("telegram_chat_id")
    return str(configured) if configured else os.environ.get("TELEGRAM_CHAT_ID")


def _record_alert(tweet_id: str | None, chat_id: str) -> None:
    try:
        with get_connection() as conn:
            log_alert(conn, tweet_id=tweet_id, chat_id=chat_id)
            conn.commit()
    except Exception:
        log.warning("Failed to log alert to database")


def send_ron_alert(
    payload: str,
    *,
    chat_id: str,
    tweet_id: str,
    timeout_seconds: int = 190,
) -> bool:
    """Ask ron's announce turn to deliver one alert, bounded by a hard timeout."""
    if not shutil.which("openclaw"):
        return False
    instruction = (
        "Real-time twag alert. Render the payload as ONE alert message per MARKET_SUMMARY_FORMAT — "
        "a single bold header line + 1-2 telegraphic bullets + the link. Add one line of context only if you know "
        "something material about this theme/position; otherwise render as-is. Never suppress a ⚠️ RESOLVED alert."
    )
    command = [
        "openclaw",
        "agent",
        "--agent",
        "default",
        "--session-id",
        f"twag-alert-{tweet_id}",
        "--thinking",
        "low",
        "--timeout",
        "180",
        "--json",
        "--deliver",
        "--reply-channel",
        "telegram",
        "--reply-account",
        "default",
        "--reply-to",
        chat_id,
        "--message",
        f"{instruction}\n\nPAYLOAD:\n{payload}",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        log.warning("Ron alert delivery failed; using direct fallback")
        return False
    if completed.returncode != 0:
        log.warning("Ron alert delivery exited nonzero; using direct fallback")
        return False
    _record_alert(tweet_id, chat_id)
    return True


def send_telegram_alert(
    message: str,
    chat_id: str | None = None,
    tweet_id: str | None = None,
) -> bool:
    """Send a Telegram alert. Returns True if successful."""
    config = load_config()
    notif_config = config.get("notifications", {})

    # Get chat ID
    if chat_id is None:
        chat_id = notif_config.get("telegram_chat_id") or os.environ.get("TELEGRAM_CHAT_ID")

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
        if response.status_code == 200:
            _record_alert(tweet_id, str(chat_id))
            return True
        return False
    except Exception:
        log.warning("Telegram send failed", exc_info=True)
        return False


def notify_high_signal_tweet(
    tweet_id: str,
    author_handle: str,
    content: str,
    score: float,
    category: str | list[str],
    summary: str,
    tickers: list[str] | None = None,
    surprise: int = 0,
    playbook_trigger: str | None = None,
    catalyst_status: str | None = None,
    themes: list[str] | None = None,
) -> bool:
    """Send notification for a high-signal tweet."""
    config = load_config()
    alert_threshold = config["scoring"]["alert_threshold"]

    if not should_alert(
        score,
        surprise,
        playbook_trigger,
        catalyst_status,
        alert_threshold=alert_threshold,
    ):
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
        surprise=surprise,
        playbook_trigger=playbook_trigger,
        catalyst_status=catalyst_status,
        themes=themes,
    )
    chat_id = _resolve_chat_id()
    if not chat_id:
        return False
    if send_ron_alert(message, chat_id=chat_id, tweet_id=tweet_id):
        return True

    from .metrics import get_collector

    get_collector().inc("notifier.fallback_direct")
    return send_telegram_alert(f"{message}\n(raw — ron unavailable)", chat_id=chat_id, tweet_id=tweet_id)
