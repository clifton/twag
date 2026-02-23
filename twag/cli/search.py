"""Search command."""

import json

import rich_click as click

from ..db import (
    FeedTweet,
    SearchResult,
    get_connection,
    get_feed_tweets,
    parse_time_range,
    query_suggests_equity_context,
    search_tweets,
)
from ._console import console


@click.command()
@click.argument("query", required=False, default=None)
@click.option("--category", "-c", help="Filter by category (fed_policy, equities, etc.)")
@click.option("--author", "-a", help="Filter by author handle")
@click.option("--min-score", "-s", type=float, help="Minimum relevance score")
@click.option("--tier", "-t", help="Filter by signal tier")
@click.option("--ticker", "-T", help="Filter by ticker symbol")
@click.option("--bookmarks", "-b", is_flag=True, help="Only bookmarked tweets")
@click.option("--since", help="Start time (YYYY-MM-DD or relative like 1d, 7d)")
@click.option("--until", help="End time (YYYY-MM-DD)")
@click.option("--today", is_flag=True, help="Since previous market close (4pm ET)")
@click.option("--time", "time_range", help="Time range shorthand (today, 7d, etc.)")
@click.option("--limit", "-n", type=int, default=20, help="Max results (default: 20)")
@click.option(
    "--order",
    "-o",
    type=click.Choice(["rank", "score", "time"]),
    default=None,
    help="Sort order: rank (BM25, requires query), score, time",
)
@click.option(
    "--format", "-f", "fmt", type=click.Choice(["brief", "full", "json"]), default="brief", help="Output format"
)
def search(
    query: str | None,
    category: str | None,
    author: str | None,
    min_score: float | None,
    tier: str | None,
    ticker: str | None,
    bookmarks: bool,
    since: str | None,
    until: str | None,
    today: bool,
    time_range: str | None,
    limit: int,
    order: str | None,
    fmt: str,
):
    """
    Search or browse tweets.

    \b
    With QUERY: full-text search using FTS5 (default order: BM25 rank).
    Without QUERY: browse recent processed tweets (default order: score).

    \b
    QUERY SYNTAX:
      Simple:    inflation fed
      Phrases:   "rate hike"
      Boolean:   inflation AND fed, fed NOT fomc
      Prefix:    infla*
      Column:    author_handle:zerohedge

    \b
    EXAMPLES:
      twag search "inflation" --today
      twag search "fed rate" -c fed_policy -s 7
      twag search "NVDA" -a zerohedge --time 7d
      twag search "earnings" --ticker AAPL
      twag search -c fed_policy -s 7 --time 7d
      twag search --today -s 8
    """
    # Parse since/until if provided as strings
    since_dt = None
    until_dt = None

    if since:
        since_dt, _ = parse_time_range(since)
    if until:
        _, until_dt = parse_time_range(until)
        if until_dt is None:
            # Try parsing as a single date for "until"
            until_parsed, until_end = parse_time_range(until)
            until_dt = until_end or until_parsed

    # Handle --today flag
    if today:
        time_range = "today"

    # Parse time_range into datetimes for browse mode
    if time_range and not query:
        parsed_since, parsed_until = parse_time_range(time_range)
        if parsed_since and since_dt is None:
            since_dt = parsed_since
        if parsed_until and until_dt is None:
            until_dt = parsed_until

    if query:
        # FTS search mode
        effective_order = order or "rank"

        # Auto-detect equity context for smart defaults (only if no time specified)
        if not time_range and since_dt is None and query_suggests_equity_context(query):
            click.echo("(auto-detected equity context, defaulting to --today)", err=True)
            time_range = "today"

        with get_connection(readonly=True) as conn:
            results = search_tweets(
                conn,
                query,
                category=category,
                author=author,
                min_score=min_score,
                signal_tier=tier,
                ticker=ticker,
                bookmarked_only=bookmarks,
                since=since_dt,
                until=until_dt,
                time_range=time_range,
                limit=limit,
                order_by=effective_order,
            )
    else:
        # Browse mode — no FTS query
        if order == "rank":
            click.echo("Warning: --order rank requires a search query; falling back to score.", err=True)
            effective_order = "score"
        else:
            effective_order = order or "score"

        # Map CLI order names to get_feed_tweets order names
        feed_order = "latest" if effective_order == "time" else "relevance"

        with get_connection(readonly=True) as conn:
            feed_results = get_feed_tweets(
                conn,
                category=category,
                ticker=ticker,
                min_score=min_score,
                signal_tier=tier,
                author=author,
                bookmarked_only=bookmarks,
                since=since_dt,
                until=until_dt,
                order_by=feed_order,
                limit=limit,
            )
        results = [_feed_tweet_to_search_result(ft) for ft in feed_results]

    if not results:
        console.print("No results found.")
        return

    if fmt == "json":
        _output_json(results)
    elif fmt == "full":
        _output_full(results)
    else:
        _output_brief(results)


def _feed_tweet_to_search_result(ft: FeedTweet) -> SearchResult:
    """Convert a FeedTweet to a SearchResult for unified output."""
    return SearchResult(
        id=ft.id,
        author_handle=ft.author_handle,
        author_name=ft.author_name,
        content=ft.content,
        summary=ft.summary,
        created_at=ft.created_at,
        relevance_score=ft.relevance_score,
        categories=ft.categories,
        signal_tier=ft.signal_tier,
        tickers=ft.tickers,
        bookmarked=ft.bookmarked,
        rank=0.0,
    )


def _output_brief(results):
    """Output search results in brief format."""
    for r in results:
        # Format: [8.2] @handle (01/15 14:32) [SPY] Summary...
        score = f"{r.relevance_score:.1f}" if r.relevance_score else "-"
        time_str = r.created_at.strftime("%m/%d %H:%M") if r.created_at else "??/??"
        tickers = f" [{','.join(r.tickers)}]" if r.tickers else ""
        bookmark = "*" if r.bookmarked else ""

        # Use summary if available, else truncate content
        text = r.summary or r.content
        text = text.replace("\n", " ")[:80]

        click.echo(f"[{score}]{bookmark} @{r.author_handle} ({time_str}){tickers} {text}")


def _output_full(results):
    """Output search results in full digest-style format."""
    for i, r in enumerate(results):
        if i > 0:
            click.echo("")
            click.echo("---")
            click.echo("")

        score = f"{r.relevance_score:.1f}" if r.relevance_score else "-"
        time_str = r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "unknown"
        categories = ", ".join(r.categories) if r.categories else "uncategorized"
        bookmark = " [BOOKMARKED]" if r.bookmarked else ""

        click.echo(f"**@{r.author_handle}** [{score}] {categories}{bookmark}")
        click.echo(f"*{time_str}*")

        if r.tickers:
            click.echo(f"Tickers: {', '.join(r.tickers)}")

        click.echo("")

        if r.summary:
            click.echo(f"**Summary:** {r.summary}")
            click.echo("")

        click.echo(r.content)
        click.echo("")
        click.echo(f"https://x.com/{r.author_handle}/status/{r.id}")


def _output_json(results):
    """Output search results as JSON."""
    output = []
    for r in results:
        output.append(
            {
                "id": r.id,
                "author_handle": r.author_handle,
                "author_name": r.author_name,
                "content": r.content,
                "summary": r.summary,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "relevance_score": r.relevance_score,
                "categories": r.categories,
                "signal_tier": r.signal_tier,
                "tickers": r.tickers,
                "bookmarked": r.bookmarked,
                "rank": r.rank,
                "url": f"https://x.com/{r.author_handle}/status/{r.id}",
            }
        )
    click.echo(json.dumps(output, indent=2))
