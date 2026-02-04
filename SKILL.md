---
name: aggregating-twitter
description: Aggregates and curates Twitter/X feed for market-relevant signals. Use when processing twitter feed, managing followed accounts, or generating daily digests.
---

# Twitter Aggregator

CLI tool for curating market-relevant Twitter content.

## Quick Start

```bash
# Fetch and process new tweets
twag fetch && twag process && twag digest

# Check what's new
twag stats --today
```

## Daily Workflow

1. **Morning fetch** (cron runs at 7 AM):
   - Fetches tier-1 accounts + home timeline
   - Stores raw tweets in SQLite

2. **Processing** (agent-triggered or cron):
   - LLM scores each tweet for relevance
   - Expands quotes, links, images for high-signal
   - Updates account weights

3. **Digest generation**:
   - Renders curated markdown to `~/.local/share/twag/digests/YYYY-MM-DD.md`
   - Or `$TWAG_DATA_DIR/digests/YYYY-MM-DD.md` if set

## What's Moving Markets?

Use `twag search` to find market-relevant signals:

```bash
# What's happening since market close?
twag search "market" --today -s 7

# Fed/macro moves
twag search "fed rate" -c fed_policy --today
twag search "inflation CPI" --today -o score
twag search "tariff" --time 7d

# Specific tickers
twag search "earnings" --ticker NVDA
twag search "guidance" --ticker AAPL --today
twag search "upgrade OR downgrade" -T TSLA

# High-signal only
twag search "breaking" --today -s 8
twag search "selloff OR rally" --today -s 7

# By author
twag search "fed" -a NickTimiraos --time 7d
twag search "market" -a zerohedge --today

# Full context on a topic
twag search "tariff china" --today -f full
```

### Search Tips

- `--today` = since previous 4pm ET market close (smart weekend handling)
- `-s 7` = high-signal tweets only (relevance score ≥7)
- `-o score` = sort by relevance score instead of text match
- `-f full` = show full tweet content with links
- `-f json` = machine-readable output

Query syntax supports: phrases (`"rate hike"`), boolean (`fed AND rate`), prefix (`infla*`).

### Categories

`fed_policy`, `inflation`, `job_market`, `macro_data`, `earnings`, `equities`, `rates_fx`, `credit`, `banks`, `consumer_spending`, `capex`, `commodities`, `energy`, `metals_mining`, `geopolitical`, `sanctions`, `tech_business`, `ai_advancement`, `crypto`, `noise`

## Common Commands

```bash
# Fetch tweets
twag fetch                      # Home + tier-1
twag fetch --source user -u @NickTimiraos  # Specific user

# Process and score
twag process                    # Score unprocessed tweets
twag process --dry-run          # Preview what would be processed

# Generate digest
twag digest                     # Today's digest
twag digest --date 2026-01-29   # Specific date

# Search (see above for more examples)
twag search "market" --today    # What's moving since close
twag search "fed" -c fed_policy # Fed policy tweets

# Account management
twag accounts list              # Show all accounts
twag accounts add @handle --tier 1  # Add tier-1 account
twag accounts promote @handle   # Promote to tier-1
twag accounts import            # Import from following.txt

# Stats
twag stats --today              # Today's statistics

# Maintenance
twag db rebuild-fts             # Rebuild search index
```

## Configuration

Config at `~/.config/twag/config.json`. Key settings:
- `llm.triage_model`: Model for fast scoring (default: haiku)
- `llm.enrichment_model`: Model for deep analysis (default: sonnet)
- `scoring.high_signal_threshold`: Score cutoff for expansion (default: 7)
- `scoring.alert_threshold`: Score cutoff for Telegram alerts (default: 8)

## Integration

Output format matches existing `memory/twitter-feed/YYYY-MM-DD.md` structure.
Implements processing pipeline from `TWITTER_MONITOR.md`.

## Telegram Digest

If you're sending a digest to Telegram, see [TELEGRAM_DIGEST_FORMAT.md](TELEGRAM_DIGEST_FORMAT.md) for the exact format to use.

See [README.md](README.md) for full CLI documentation.
