"""Markdown output generation for digests."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .article_visuals import build_article_visuals
from .config import get_digests_dir, load_config
from .db import get_connection, get_tweet_by_id, get_tweets_for_digest, mark_tweet_in_digest
from .fetcher import get_tweet_url
from .link_utils import normalize_tweet_links


def _value(tweet: sqlite3.Row | dict, key: str, default=None):
    if isinstance(tweet, sqlite3.Row):
        try:
            return tweet[key]
        except (IndexError, KeyError):
            return default
    return tweet.get(key, default)


def render_digest(
    date: str | None = None,
    min_score: float | None = None,
    output_path: Path | None = None,
) -> str:
    """Render a digest for the given date. Returns markdown content."""
    config = load_config()

    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    if min_score is None:
        min_score = config["scoring"]["min_score_for_digest"]

    with get_connection() as conn:
        tweets = get_tweets_for_digest(conn, date=date, min_score=min_score)

        if not tweets:
            return f"# Twitter Feed - {date}\n\n*No market-relevant tweets found.*\n"

        # Group by signal tier
        high_signal = []
        market_relevant = []
        news = []

        for tweet in tweets:
            tier = tweet["signal_tier"] or "noise"
            if tier == "high_signal":
                high_signal.append(tweet)
            elif tier == "market_relevant":
                market_relevant.append(tweet)
            elif tier == "news":
                news.append(tweet)

        # Render markdown
        lines = [
            f"# Twitter Feed - {date}",
            "",
            f"*Generated: {datetime.now().strftime('%I:%M %p')}*",
            "",
        ]

        if high_signal:
            lines.extend(
                [
                    "---",
                    "",
                    "## 🔥 High Signal",
                    "",
                ]
            )
            for tweet in high_signal:
                lines.extend(_render_tweet(conn, tweet))
                mark_tweet_in_digest(conn, tweet["id"], date)

        if market_relevant:
            lines.extend(
                [
                    "---",
                    "",
                    "## 📈 Market Relevant",
                    "",
                ]
            )
            for tweet in market_relevant:
                lines.extend(_render_tweet(conn, tweet))
                mark_tweet_in_digest(conn, tweet["id"], date)

        if news:
            lines.extend(
                [
                    "---",
                    "",
                    "## 📰 News/Context",
                    "",
                ]
            )
            for tweet in news:
                lines.extend(_render_tweet(conn, tweet, compact=True))
                mark_tweet_in_digest(conn, tweet["id"], date)

        conn.commit()

    content = "\n".join(lines)

    # Write to file if path provided
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)
    elif output_path is None:
        # Default to digests dir
        digests_dir = get_digests_dir()
        default_path = digests_dir / f"{date}.md"
        default_path.parent.mkdir(parents=True, exist_ok=True)
        default_path.write_text(content)

    return content


def _render_tweet(conn: sqlite3.Connection, tweet: sqlite3.Row, compact: bool = False) -> list[str]:
    """Render a single tweet to markdown lines."""
    lines = []

    # Parse created_at for display
    created_str = tweet["created_at"] or ""
    time_str = ""
    if created_str:
        try:
            dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            time_str = dt.strftime("%I:%M %p")
        except ValueError:
            pass

    handle = tweet["author_handle"]
    url = get_tweet_url(tweet["id"], handle)
    links = []
    if _value(tweet, "links_json"):
        try:
            decoded = json.loads(_value(tweet, "links_json"))
            if isinstance(decoded, list):
                links = [item for item in decoded if isinstance(item, dict)]
        except json.JSONDecodeError:
            links = []
    normalized_links = normalize_tweet_links(
        tweet_id=tweet["id"],
        text=tweet["content"],
        links=links,
        has_media=bool(_value(tweet, "has_media", False)),
    )
    inline_tweet_links = normalized_links.inline_tweet_links
    external_links = normalized_links.external_links

    # Bookmark flag
    is_bookmarked = _value(tweet, "bookmarked", False)
    bookmark_badge = " ⭐" if is_bookmarked else ""

    # Check if tweet has a content summary (long non-tier-1 tweets)
    content_summary = _value(tweet, "content_summary")
    is_summarized = bool(content_summary)

    if compact:
        # One-liner format for news tier
        summary = tweet["summary"] or tweet["content"][:100]
        tickers = ""
        if tweet["tickers"]:
            try:
                ticker_list = json.loads(tweet["tickers"])
                if ticker_list:
                    tickers = f" [{', '.join(ticker_list)}]"
            except json.JSONDecodeError:
                pass
        lines.append(f"- {bookmark_badge}**@{handle}**: {summary}{tickers} ([link]({url}))")
        lines.append("")
    else:
        # Full format for high signal / market relevant
        lines.append(f"### @{handle}{bookmark_badge} ({time_str})")
        lines.append("")

        # Show summarized content or full content
        if is_summarized:
            lines.append("*SUMMARIZED*")
            lines.append("")
            lines.append(content_summary)
        else:
            lines.append(normalized_links.display_text or tweet["content"])
        lines.append("")

        # Summary/insight
        if tweet["summary"]:
            lines.append(f"💡 **Insight:** {tweet['summary']}")
            lines.append("")

        # Tickers
        if tweet["tickers"]:
            try:
                ticker_list = json.loads(tweet["tickers"])
                if ticker_list:
                    lines.append(f"📊 **Tickers:** {', '.join(ticker_list)}")
                    lines.append("")
            except json.JSONDecodeError:
                pass

        # Categories (stored as JSON array or legacy string)
        if tweet["category"]:
            try:
                categories = json.loads(tweet["category"])
                if isinstance(categories, str):
                    categories = [categories]
            except json.JSONDecodeError:
                categories = [tweet["category"]]

            # Filter out noise
            categories = [c for c in categories if c != "noise"]
            if categories:
                cat_display = ", ".join(c.replace("_", " ").title() for c in categories)
                lines.append(f"🏷️ **Categories:** {cat_display}")
                lines.append("")

        # Link summary
        has_article_sections = bool(_value(tweet, "is_x_article") and _value(tweet, "article_summary_short"))
        if tweet["media_analysis"] and not has_article_sections:
            lines.append("📊 **Chart Analysis:**")
            lines.append(f"> {tweet['media_analysis']}")
            lines.append("")

        if has_article_sections:
            lines.append("🧾 **Article Summary:**")
            lines.append(f"> {tweet['article_summary_short']}")
            lines.append("")

            article_top_visual = None
            if _value(tweet, "article_top_visual_json"):
                try:
                    decoded = json.loads(_value(tweet, "article_top_visual_json"))
                    if isinstance(decoded, dict) and decoded.get("url"):
                        article_top_visual = decoded
                except json.JSONDecodeError:
                    article_top_visual = None

            article_points = []
            if _value(tweet, "article_primary_points_json"):
                try:
                    decoded = json.loads(_value(tweet, "article_primary_points_json"))
                    if isinstance(decoded, list):
                        article_points = [item for item in decoded if isinstance(item, dict)]
                except json.JSONDecodeError:
                    article_points = []
            if article_points:
                lines.append("📌 **Primary Points:**")
                for item in article_points[:4]:
                    point = (item.get("point") or "").strip()
                    reasoning = (item.get("reasoning") or "").strip()
                    if not point:
                        continue
                    if reasoning:
                        lines.append(f"- {point} — {reasoning}")
                    else:
                        lines.append(f"- {point}")
                lines.append("")

            article_actions = []
            if _value(tweet, "article_action_items_json"):
                try:
                    decoded = json.loads(_value(tweet, "article_action_items_json"))
                    if isinstance(decoded, list):
                        article_actions = [item for item in decoded if isinstance(item, dict)]
                except json.JSONDecodeError:
                    article_actions = []
            if article_actions:
                lines.append("✅ **Actionable Items:**")
                for item in article_actions[:3]:
                    action = (item.get("action") or "").strip()
                    trigger = (item.get("trigger") or "").strip()
                    if not action:
                        continue
                    if trigger:
                        lines.append(f"- {action} (trigger: {trigger})")
                    else:
                        lines.append(f"- {action}")
                lines.append("")

            article_media_items: list[dict] = []
            media_raw = _value(tweet, "media_items")
            if media_raw:
                try:
                    decoded = json.loads(media_raw)
                    if isinstance(decoded, list):
                        article_media_items = [item for item in decoded if isinstance(item, dict)]
                except json.JSONDecodeError:
                    article_media_items = []
            visuals = build_article_visuals(
                top_visual=article_top_visual,
                media_items=article_media_items,
                max_items=5,
            )
            if visuals:
                lines.append("🖼️ **Visuals:**")
                for idx, visual in enumerate(visuals, start=1):
                    kind = str(visual.get("kind") or "visual")
                    top_suffix = " (top)" if visual.get("is_top") else ""
                    takeaway = str(visual.get("key_takeaway") or "").strip()
                    url_text = str(visual.get("url") or "").strip()
                    if takeaway:
                        lines.append(f"- {idx}. {kind}{top_suffix}: {takeaway}")
                    else:
                        lines.append(f"- {idx}. {kind}{top_suffix}")
                    if url_text:
                        lines.append(f"  - {url_text}")
                lines.append("")
        elif tweet["link_summary"]:
            lines.append("🔗 **Linked Article:**")
            lines.append(f"> {tweet['link_summary']}")
            lines.append("")

        if external_links:
            lines.append("🌐 **Links:**")
            for link in external_links[:4]:
                url_text = link.get("url") or ""
                if not url_text:
                    continue
                lines.append(f"- [{link.get('display_url') or url_text}]({url_text})")
            lines.append("")

        if inline_tweet_links:
            lines.append("💬 **Linked Tweets:**")
            for link in inline_tweet_links[:3]:
                linked_id = link.get("id")
                linked_url = link.get("url") or get_tweet_url(linked_id or "", "i")
                if not linked_id:
                    continue
                linked_row = get_tweet_by_id(conn, linked_id)
                if linked_row and linked_row["summary"]:
                    linked_handle = linked_row["author_handle"] or "unknown"
                    lines.append(f"- **@{linked_handle}**: {linked_row['summary']} ([link]({linked_url}))")
                elif linked_row and linked_row["content"]:
                    linked_handle = linked_row["author_handle"] or "unknown"
                    preview = linked_row["content"][:180].strip()
                    lines.append(f"- **@{linked_handle}**: {preview} ([link]({linked_url}))")
                else:
                    lines.append(f"- [Tweet {linked_id}]({linked_url})")
            lines.append("")

        lines.append(f"[View tweet]({url})")
        lines.append("")
        lines.append("---")
        lines.append("")

    return lines


def get_digest_path(date: str | None = None) -> Path:
    """Get the path for a digest file."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    return get_digests_dir() / f"{date}.md"
