---
name: twag
description: Twitter/X market signal aggregator. Fetches tweets via bird CLI, scores them with LLMs, generates digests, and serves a web feed. Use when processing Twitter/X feeds, searching market-relevant tweets, generating digests, or managing followed accounts.
allowed-tools: Bash(twag:*) Bash(bird:*)
---

# twag — Twitter/X Market Signal Aggregator

## Prerequisites

- `twag` CLI installed (`pip install twag` or `pip install -e .` from repo root)
- `bird` CLI installed (`npm install -g @steipete/bird` or `brew install steipete/tap/bird`)
- Environment variables: `AUTH_TOKEN`, `CT0` (Twitter cookies), `GEMINI_API_KEY`
- Optional: `ANTHROPIC_API_KEY` (enrichment), `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` (alerts)

Verify setup: `twag doctor`

## Core Pipeline

```bash
twag fetch && twag process && twag digest
```

- **fetch** — pulls tweets from home timeline, tier-1 accounts, bookmarks
- **process** — LLM-scores unprocessed tweets for market relevance
- **digest** — generates a formatted digest of high-signal tweets

## Common Workflows

### Browse high-signal tweets

```bash
twag search --today -s 7
twag search --time 2h -s 6 -f json -n 50
```

### Full-text search

```bash
twag search "query"                     # Basic FTS5 search
twag search "query" -c fed_policy       # Filter by category
twag search "query" -a handle           # Filter by author
twag search "query" --ticker AAPL       # Filter by ticker
twag search "query" --today -s 7        # Today, high-signal only
twag search "query" --format json       # JSON output
```

Query syntax: simple words, `"phrase"`, `AND`/`NOT` boolean, `prefix*` wildcard.

### Analyze a single tweet

```bash
twag analyze https://x.com/user/status/123456789
twag analyze 123456789 --reprocess
```

### Account management

```bash
twag accounts list
twag accounts add @handle -t 1          # Add as tier-1
twag accounts promote @handle
twag accounts mute @handle
```

### Stats and maintenance

```bash
twag stats --today
twag prune --days 14
twag db rebuild-fts
```

### Web UI

```bash
twag web                                # Starts on localhost:5173
```

## Scoring Tiers

| Score | Level | Behavior |
|-------|-------|----------|
| 8-10 | Alert | Telegram notification |
| 7 | High signal | Enriched, included in digests |
| 5-6 | Market relevant | Included in digests |
| 3-4 | News/context | Searchable only |
| 0-2 | Noise | Filtered out |

## Categories

`fed_policy`, `inflation`, `job_market`, `macro_data`, `earnings`, `equities`, `rates_fx`, `credit`, `banks`, `consumer_spending`, `capex`, `commodities`, `energy`, `metals_mining`, `geopolitical`, `sanctions`, `tech_business`, `ai_advancement`, `crypto`, `noise`

## Telegram Digest

When creating Telegram digests, read `TELEGRAM_DIGEST_FORMAT.md` for formatting rules. Key points:

- Use `twag search --time Xh -s 6 -f json -n 50` for structured input
- Group tweets by theme, not chronologically
- Use `**BOLD CAPS**` for section headers
- Citations: `[📊](url)` for media tweets, `[🔗](url)` otherwise
