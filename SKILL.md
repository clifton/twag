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
metadata:
  openclaw:
    emoji: "📊"
    requires:
      bins: ["twag", "bird"]
      env: ["GEMINI_API_KEY", "AUTH_TOKEN", "CT0"]
    install:
      - id: pip
        kind: pip
        package: twag
        bins: ["twag"]
        label: "Install twag (pip)"
      - id: bird-npm
        kind: node
        package: "@steipete/bird"
        bins: ["bird"]
        label: "Install bird CLI (npm)"
      - id: bird-brew
        kind: brew
        formula: "steipete/tap/bird"
        bins: ["bird"]
        label: "Install bird CLI (brew)"
        os: ["darwin"]
allowed-tools: Bash(twag:*), Bash(bird:*)
---

# twag — Twitter/X Market Signal Aggregator

## Installation

### Step 1: Install bird CLI (Twitter access)

bird is required for Twitter/X API access. Install via npm:

```bash
npm install -g @steipete/bird
```

Or on macOS via Homebrew:

```bash
brew install steipete/tap/bird
```

Verify: `bird --version`

### Step 2: Configure Twitter auth

bird uses cookie-based auth. The user must provide two cookies from their browser:

- `AUTH_TOKEN` — The `auth_token` cookie from x.com
- `CT0` — The `ct0` cookie from x.com

Set as environment variables:

```bash
export AUTH_TOKEN="..."
export CT0="..."
```

Or add to `~/.env` (twag sources this automatically).

Verify auth: `bird whoami`

### Step 3: Install twag

```bash
pip install twag
```

Or from source:

```bash
git clone https://github.com/clifton/twag.git
cd twag && pip install -e .
```

### Step 4: Initialize and verify

```bash
twag init
twag doctor
```

### Step 5: Set LLM API key

```bash
export GEMINI_API_KEY="..."  # Required
export ANTHROPIC_API_KEY="..."  # Optional, for enrichment
```

## Quick Reference

```bash
# Full pipeline
twag fetch && twag process && twag digest

# Search high-signal tweets
twag search "market" --today -s 7

# Check stats
twag stats --today
```

## Common Workflows

### Morning market check

```bash
twag fetch && twag process
twag search "market" --today -s 7
twag digest --stdout
```

### Track specific topic

```bash
twag search "fed rate" -c fed_policy --today
twag search "powell" -a NickTimiraos --time 7d
```

### Monitor ticker

```bash
twag search "earnings" --ticker NVDA --today
twag search "AAPL" -s 6 --time 7d
```

### Analyze single tweet

```bash
twag analyze https://x.com/user/status/123456789
twag analyze 123456789 --reprocess  # Force re-analyze
```

## Commands

### Search (most common)

```bash
twag search "query"                  # Full-text search
twag search "query" -c fed_policy    # Filter by category
twag search "query" -a handle        # Filter by author
twag search "query" --ticker AAPL    # Filter by ticker
twag search "query" --today          # Since last market close
twag search "query" --time 7d        # Last N days
twag search "query" -s 7             # Min score threshold
twag search "query" --format full    # Digest-style output
twag search "query" --format json    # JSON output
```

**Query syntax:**
- Simple: `inflation fed` (matches both)
- Phrase: `"rate hike"` (exact)
- Boolean: `inflation AND fed`, `fed NOT fomc`
- Prefix: `infla*` (wildcard)

### Fetch & Process

```bash
twag fetch                    # Home + tier-1 + bookmarks
twag fetch --no-tier1         # Home only
twag fetch -u @handle         # Specific user
twag fetch --source search -q "query"  # Search tweets

twag process                  # Score unprocessed
twag process -n 100           # Limit batch
twag process --dry-run        # Preview
twag process --no-notify      # Skip alerts
```

### Digest

```bash
twag digest                   # Today's digest (saves to file)
twag digest --stdout          # Output to terminal
twag digest -d 2026-01-29     # Specific date
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
twag accounts boost @handle --amount 10
twag accounts decay           # Apply daily decay
```

### Stats & Maintenance

```bash
twag stats                    # All-time
twag stats --today            # Today
twag prune --days 14          # Delete old tweets
twag export --days 7          # Export recent
```

### Database

```bash
twag db path                  # Show location
twag db shell                 # SQLite shell
twag db rebuild-fts           # Rebuild search index
twag db dump                  # Backup
twag db restore backup.sql    # Restore
```

### Web UI

```bash
twag web                      # Start (localhost:5173)
twag web --host 127.0.0.1     # Localhost only
twag web --port 8080          # Custom port
```

### Config

```bash
twag config show              # Show config
twag config path              # Show path
twag config set key value     # Update setting
```

## Scoring Tiers

| Score | Level | Behavior |
|-------|-------|----------|
| 8-10 | High signal | Telegram alert |
| 6-7 | Market relevant | In digests |
| 4-5 | News/context | Searchable |
| 0-3 | Noise | Filtered out |

## Categories

`fed_policy`, `inflation`, `job_market`, `macro_data`, `earnings`, `equities`, `rates_fx`, `credit`, `banks`, `consumer_spending`, `commodities`, `energy`, `geopolitical`, `tech_business`, `ai_advancement`, `crypto`

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `AUTH_TOKEN` | Yes | Twitter auth cookie |
| `CT0` | Yes | Twitter ct0 cookie |
| `GEMINI_API_KEY` | Yes | LLM triage |
| `ANTHROPIC_API_KEY` | No | Enrichment |
| `TELEGRAM_BOT_TOKEN` | No | Alerts |
| `TELEGRAM_CHAT_ID` | No | Alert destination |

## Telegram Digest Format

When sending digests to Telegram, follow [{baseDir}/TELEGRAM_DIGEST_FORMAT.md]({baseDir}/TELEGRAM_DIGEST_FORMAT.md):

- Group tweets by theme (don't list chronologically)
- Use `**BOLD CAPS**` for section headers (no markdown `###`)
- Use `•` for bullet points
- Citations: `[🔗](url)` for links, `[📊](url)` for charts
- Condense multiple tweets on same topic into bullets
- Extract key facts and numbers

## Automation

See [{baseDir}/SUGGESTED_CRON_SCHEDULE.md]({baseDir}/SUGGESTED_CRON_SCHEDULE.md) for:

- systemd/launchd timers for data collection (every 15 min)
- OpenClaw cron jobs for Telegram digest delivery

## Troubleshooting

### bird not found

```bash
npm install -g @steipete/bird
```

### Auth errors (401)

```bash
# Check cookies are set
bird whoami

# If expired, get fresh cookies from x.com
```

### Query ID errors (404)

```bash
bird query-ids --fresh
```

### Database issues

```bash
twag db rebuild-fts
```

## Links

- **twag:** https://github.com/clifton/twag
- **bird:** https://github.com/steipete/bird
- **OpenClaw:** https://github.com/openclaw/openclaw
