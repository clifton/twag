---
name: twag
description: Twitter/X market signal aggregator with LLM-powered scoring. Fetches tweets via bird CLI, scores for market relevance, generates digests, and serves a web feed. Use when processing Twitter/X feeds for market signals, searching for market-relevant tweets, generating daily tweet digests, managing followed Twitter accounts, finding tweets about specific tickers or topics, or automating market analysis workflows.
allowed-tools: Bash(twag:*) Bash(bird:*)
compatibility: Requires Python 3.10+, bird CLI (npm or brew), and API keys (GEMINI_API_KEY required, ANTHROPIC_API_KEY optional)
metadata:
  author: clifton
  version: "1.0"
---

# twag — Twitter/X Market Signal Aggregator

A pipeline that fetches tweets via the `bird` CLI, scores them for market relevance using LLMs, generates digests, and serves a web feed.

## Architecture

```
FETCH → PROCESS → DIGEST
```

## Quick Start

```bash
twag init          # Initialize database and config
twag doctor        # Verify setup
twag fetch         # Fetch tweets from timeline + tier-1 accounts
twag process       # Score tweets with LLM
twag digest        # Generate daily digest
```

## Common Workflows

### Full pipeline

```bash
twag fetch && twag process && twag digest
```

### Morning market check

```bash
twag fetch && twag process
twag search --today -s 7
twag digest --stdout
```

### Search tweets

```bash
# Browse high-signal tweets
twag search --today -s 7

# Rich JSON for agent consumption
twag search --time 2h -s 6 -f json -n 50

# Full-text search with filters
twag search "fed rate" -c fed_policy --today
twag search "AAPL" -s 6 --time 7d --ticker AAPL
```

### Analyze single tweet

```bash
twag analyze https://x.com/user/status/123456789
twag analyze 123456789 --reprocess
```

### Account management

```bash
twag accounts list              # All accounts
twag accounts add @handle -t 1  # Add as tier-1
twag accounts promote @handle   # Promote to tier-1
twag accounts mute @handle      # Mute account
```

## Commands

| Command | Purpose |
|---------|---------|
| `twag fetch` | Fetch tweets (home + tier-1 + bookmarks) |
| `twag process` | Score unprocessed tweets with LLM |
| `twag digest` | Generate market digest |
| `twag search` | Full-text search and browse tweets |
| `twag analyze` | Analyze a single tweet URL or ID |
| `twag accounts` | Manage followed accounts (list/add/promote/demote/mute/boost/decay/import) |
| `twag stats` | Show tweet statistics |
| `twag prune` | Delete old tweets |
| `twag export` | Export tweets |
| `twag config` | Show/set configuration (show/path/set) |
| `twag db` | Database operations (path/shell/init/rebuild-fts/dump/restore) |
| `twag web` | Start web UI |
| `twag init` | Initialize twag |
| `twag narratives` | Manage emerging narratives (list) |
| `twag doctor` | Verify setup |

## Search Query Syntax

- Simple: `inflation fed` (matches both)
- Phrase: `"rate hike"` (exact match)
- Boolean: `inflation AND fed`, `fed NOT fomc`
- Prefix: `infla*` (wildcard)

## Scoring Tiers

| Score | Level | Behavior |
|-------|-------|----------|
| 8-10 | Alert | Telegram alert (when --notify) |
| 7 | High signal | Enriched, included in digests |
| 5-6 | Market relevant | Included in digests |
| 3-4 | News/context | Searchable only |
| 0-2 | Noise | Filtered out |

## Categories

`fed_policy`, `inflation`, `job_market`, `macro_data`, `earnings`, `equities`, `rates_fx`, `credit`, `banks`, `consumer_spending`, `capex`, `commodities`, `energy`, `metals_mining`, `geopolitical`, `sanctions`, `tech_business`, `ai_advancement`, `crypto`, `noise`

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `AUTH_TOKEN` | Yes | Twitter auth cookie |
| `CT0` | Yes | Twitter ct0 cookie |
| `GEMINI_API_KEY` | Yes | LLM triage |
| `ANTHROPIC_API_KEY` | No | Enrichment |
| `TELEGRAM_BOT_TOKEN` | No | Alerts |
| `TELEGRAM_CHAT_ID` | No | Alert destination |
