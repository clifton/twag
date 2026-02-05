"""FastAPI application for twag web interface."""

import html
import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import get_database_path
from ..db import init_db
from .routes import context, prompts, reactions, tweets

# Template and static paths
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

_TWEET_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:mobile\.)?(?:x|twitter)\.com/(?:i/(?:web/)?|[^/]+/)?status/(\d+)(?:\?[^\s]+)?",
    re.IGNORECASE,
)


def _parse_created_at(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_tweet_links(text: str) -> list[tuple[str, str]]:
    return [(match.group(1), match.group(0)) for match in _TWEET_URL_RE.finditer(text)]


def _remove_tweet_links(text: str, links: list[tuple[str, str]], remove_ids: set[str]) -> str:
    cleaned = text
    for tweet_id, url in links:
        if tweet_id not in remove_ids:
            continue
        cleaned = re.sub(rf"\s*{re.escape(url)}", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _quote_embed_from_row(row) -> dict[str, str | None]:
    created_at = _parse_created_at(row["created_at"])
    return {
        "id": row["id"],
        "author_handle": row["author_handle"],
        "author_name": row["author_name"],
        "content": row["content"],
        "created_at": created_at.isoformat() if created_at else None,
    }


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Twag",
        description="Twitter aggregator web interface",
        version="0.1.0",
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Set up templates
    templates = Jinja2Templates(directory=TEMPLATES_DIR)

    # Add custom filter for HTML entity unescaping (handles None)
    templates.env.filters["unescape"] = lambda s: html.unescape(s) if s else s

    # Store templates in app state for routes to access
    app.state.templates = templates
    app.state.db_path = get_database_path()

    # Initialize database
    init_db(app.state.db_path)

    # Include routers
    app.include_router(tweets.router, prefix="/api")
    app.include_router(reactions.router, prefix="/api")
    app.include_router(prompts.router, prefix="/api")
    app.include_router(context.router, prefix="/api")

    # Main page routes
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """Main feed page."""
        return templates.TemplateResponse(
            "feed.html",
            {"request": request},
        )

    @app.get("/prompts", response_class=HTMLResponse)
    async def prompts_page(request: Request):
        """Prompt editor page."""
        return templates.TemplateResponse(
            "prompts.html",
            {"request": request},
        )

    @app.get("/context-commands", response_class=HTMLResponse)
    async def context_commands_page(request: Request):
        """Context commands management page."""
        return templates.TemplateResponse(
            "context.html",
            {"request": request},
        )

    # htmx partial routes
    @app.get("/feed", response_class=HTMLResponse)
    async def feed_partial(
        request: Request,
        category: str | None = None,
        ticker: str | None = None,
        min_score: float | None = None,
        signal_tier: str | None = None,
        author: str | None = None,
        bookmarked: bool = False,
        since: str | None = None,
        sort: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        """Feed partial for htmx infinite scroll."""
        from ..db import get_connection, get_feed_tweets, get_tweet_by_id, parse_time_range

        # Parse time range
        since_dt = None
        if since:
            since_dt, _ = parse_time_range(since)

        with get_connection(app.state.db_path) as conn:
            tweets_list = get_feed_tweets(
                conn,
                category=category,
                ticker=ticker,
                min_score=min_score,
                signal_tier=signal_tier,
                author=author,
                bookmarked_only=bookmarked,
                since=since_dt,
                order_by=sort or "relevance",
                limit=limit,
                offset=offset,
            )

            for tweet in tweets_list:
                content = tweet.content or ""
                links = _extract_tweet_links(content)
                link_map: dict[str, str] = {}
                for tweet_id, url in links:
                    if tweet_id and tweet_id not in link_map:
                        link_map[tweet_id] = url

                inline_quote_id = None
                if not tweet.has_quote:
                    for tweet_id in link_map:
                        if tweet_id and tweet_id != tweet.id:
                            inline_quote_id = tweet_id
                            break

                quote_id = tweet.quote_tweet_id or inline_quote_id
                if quote_id == tweet.id:
                    quote_id = None
                quote_row = get_tweet_by_id(conn, quote_id) if quote_id else None

                tweet.quote_embed = _quote_embed_from_row(quote_row) if quote_row else None
                tweet.quote_link_id = quote_id

                reference_links: list[dict[str, str]] = []
                for tweet_id, url in link_map.items():
                    if tweet_id == tweet.id:
                        continue
                    if quote_id and tweet_id == quote_id:
                        continue
                    reference_links.append({"id": tweet_id, "url": url})

                tweet.reference_links = reference_links

                remove_ids = set(link_map.keys())
                remove_ids.add(tweet.id)

                tweet.display_content = _remove_tweet_links(content, links, remove_ids) if content else content

        return templates.TemplateResponse(
            "partials/tweets.html",
            {
                "request": request,
                "tweets": tweets_list,
                "offset": offset + limit,
                "has_more": len(tweets_list) == limit,
                # Pass filter params for next page
                "category": category,
                "ticker": ticker,
                "min_score": min_score,
                "signal_tier": signal_tier,
                "author": author,
                "bookmarked": bookmarked,
                "since": since,
                "sort": sort,
            },
        )

    @app.get("/tweet/{tweet_id}", response_class=HTMLResponse)
    async def tweet_detail(request: Request, tweet_id: str):
        """Single tweet detail view."""
        from ..db import get_connection, get_reactions_for_tweet, get_tweet_by_id
        from ..media import parse_media_items

        with get_connection(app.state.db_path) as conn:
            tweet = get_tweet_by_id(conn, tweet_id)
            reactions_list = get_reactions_for_tweet(conn, tweet_id) if tweet else []

        if tweet:
            tweet = dict(tweet)
            tweet["media_items"] = parse_media_items(tweet.get("media_items"))

        return templates.TemplateResponse(
            "partials/tweet_detail.html",
            {
                "request": request,
                "tweet": tweet,
                "reactions": reactions_list,
            },
        )

    return app
