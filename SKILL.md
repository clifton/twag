---
name: twag
description: Twitter/X aggregator for market-relevant signals with LLM-powered scoring. Fetches, processes, and curates tweets for market analysis.
read_when:
  - Processing Twitter/X feed for market signals
  - Searching for market-relevant tweets
  - Generating daily tweet digests
  - Managing followed Twitter accounts
  - Finding tweets about specific tickers or topics
homepage: https://github.com/clifton/twag
metadata: {"clawdbot":{"emoji":"📊","requires":{"bins":["twag","bird"],"env":["GEMINI_API_KEY","AUTH_TOKEN","CT0"]},"install":[{"id":"pip","kind":"pip","package":"twag","bins":["twag"],"label":"Install twag (pip)"}]}}
allowed-tools: Bash(twag:*)
---

# Twitter Aggregator (twag)

## Installation

### pip (recommended)

```bash
pip install twag
npm install -g @anthropics/bird
twag init
twag doctor
```

### From Source

```bash
git clone https://github.com/clifton/twag.git
cd twag
pip install -e .
twag init
```

## Quick start

```bash
twag fetch && twag process && twag digest   # Full cycle
twag stats --today                          # Check what's new
twag search "market" --today -s 7           # Search high-signal tweets
```

## Core workflow

1. **Fetch**: `twag fetch` - Pull tweets from timeline and tier-1 accounts
2. **Process**: `twag process` - Score tweets with LLM (0-10), categorize, enrich
3. **Digest**: `twag digest` - Generate markdown summary of high-signal content

## Commands

### Search (most common)

```bash
twag search "inflation fed"              # Full-text search
twag search "rate hike" -c fed_policy    # Filter by category
twag search "NVDA" -a zerohedge          # Filter by author
twag search "earnings" --ticker AAPL     # Filter by ticker
twag search "breaking" --today -s 8      # High-signal since market close
twag search "fed" --time 7d              # Last 7 days
twag search "macro" --bookmarks          # Bookmarked only
twag search "fed" --format full          # Digest-style output
twag search "fed" --format json          # JSON output
```

**Query syntax:**
- Simple: `inflation fed` (matches both)
- Phrase: `"rate hike"` (exact)
- Boolean: `inflation AND fed`, `fed NOT fomc`
- Prefix: `infla*` (wildcard)

**Time filters:**
- `--today`: Since previous 4pm ET market close
- `--time 7d`: Last 7 days
- `--since 2026-01-15`: From specific date

### Fetch & Process

```bash
twag fetch                    # Home timeline + tier-1 accounts
twag fetch --no-tier1         # Home only
twag fetch -u @NickTimiraos   # Specific user
twag fetch --source search -q "Fed Powell"  # Search tweets

twag process                  # Score unprocessed tweets
twag process -n 100           # Limit batch size
twag process --dry-run        # Preview only
twag process --no-notify      # Skip Telegram alerts
```

### Digest

```bash
twag digest                   # Generate today's digest
twag digest -d 2026-01-29     # Specific date
twag digest --stdout          # Output to terminal
twag digest --min-score 6     # Custom threshold
```

### Account Management

```bash
twag accounts list            # All accounts
twag accounts list -t 1       # Tier-1 only
twag accounts add @handle     # Add account
twag accounts add @handle -t 1  # Add as tier-1
twag accounts promote @handle # Promote to tier-1
twag accounts mute @handle    # Mute account
twag accounts boost @handle --amount 10  # Boost weight
twag accounts decay           # Apply daily decay
twag accounts import          # Import from following.txt
```

### Stats & Maintenance

```bash
twag stats                    # All-time stats
twag stats --today            # Today's stats
twag stats -d 2026-01-29      # Specific date

twag prune --days 14          # Delete old tweets
twag prune --days 14 --dry-run  # Preview prune
twag export --days 7          # Export recent data
```

### Database

```bash
twag db path                  # Show database location
twag db shell                 # Open SQLite shell
twag db rebuild-fts           # Rebuild search index
```

### Web Interface

```bash
twag web                      # Start web UI (default: localhost:5000)
twag web --port 8080          # Custom port
```

### Configuration

```bash
twag config show              # Show current config
twag config path              # Show config file path
twag config set llm.triage_model gemini-3-flash-preview
twag config set scoring.alert_threshold 9
```

## Examples

### Morning market check

```bash
twag fetch && twag process
twag search "market" --today -s 7
twag digest --stdout
```

### Track Fed commentary

```bash
twag search "fed rate" -c fed_policy --today
twag search "powell" -a NickTimiraos --time 7d
```

### Monitor specific ticker

```bash
twag search "earnings guidance" --ticker NVDA --today
twag search "AAPL" -s 6 --time 7d
```

### Find high-signal breaking news

```bash
twag search "breaking" --today -s 8
```

## Categories

`fed_policy`, `inflation`, `job_market`, `macro_data`, `earnings`, `equities`, `rates_fx`, `credit`, `banks`, `consumer_spending`, `commodities`, `energy`, `geopolitical`, `tech_business`, `ai_advancement`, `crypto`

## Configuration

Config file: `~/.config/twag/config.json`

Key settings:
- `llm.triage_model`: Model for scoring (default: gemini-3-flash-preview)
- `scoring.alert_threshold`: Score threshold for Telegram alerts (default: 8)
- `paths.data_dir`: Custom data directory

## Environment Variables

**Required:**
- `GEMINI_API_KEY` - Google Gemini API key for triage/vision
- `AUTH_TOKEN` - Twitter auth token (from browser cookies)
- `CT0` - Twitter CT0 token (from browser cookies)

**Optional:**
- `ANTHROPIC_API_KEY` - For enrichment (higher-quality summaries)
- `TELEGRAM_BOT_TOKEN` - For real-time alerts
- `TELEGRAM_CHAT_ID` - Telegram chat for alerts
- `TWAG_DATA_DIR` - Override data directory

## Notes

- Uses `bird` CLI for Twitter API access
- Scores range 0-10: 7+ is high signal, 8+ triggers alerts
- `--today` means since previous 4pm ET market close
- Data stored in `~/.local/share/twag/` by default

## Reporting Issues

https://github.com/clifton/twag/issues
