"""Markdown output generation for digests."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import get_digests_dir, load_config
from .db import get_connection, get_tweets_for_digest, mark_tweet_in_digest
from .fetcher import get_tweet_url


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
                lines.extend(_render_tweet(tweet))
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
                lines.extend(_render_tweet(tweet))
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
                lines.extend(_render_tweet(tweet, compact=True))
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


def _render_tweet(tweet: sqlite3.Row, compact: bool = False) -> list[str]:
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

    # Bookmark flag
    is_bookmarked = tweet.get("bookmarked", False)
    bookmark_badge = " ⭐" if is_bookmarked else ""

    # Check if tweet has a content summary (long non-tier-1 tweets)
    content_summary = tweet.get("content_summary")
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
            lines.append(tweet["content"])
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

        # Media analysis
        if tweet["media_analysis"]:
            lines.append("📊 **Chart Analysis:**")
            lines.append(f"> {tweet['media_analysis']}")
            lines.append("")

        # Link summary
        if tweet["link_summary"]:
            lines.append("🔗 **Linked Article:**")
            lines.append(f"> {tweet['link_summary']}")
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
