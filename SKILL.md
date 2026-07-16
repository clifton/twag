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
      bins: ["twag", "bird", "spine"]
      env: ["GEMINI_API_KEY", "AUTH_TOKEN", "CT0"]
    install:
      - id: uv
        kind: uv
        package: twag
        bins: ["twag"]
        label: "Install twag (uv tool)"
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
uv tool install twag
```

Or from source:

```bash
git clone https://github.com/clifton/twag.git
cd twag && uv tool install --editable .
```

The global `twag` launcher is managed by uv. Inside a development checkout, use `uv run twag ...` to run against the
checkout and its locked environment.

### Step 4: Initialize and verify

```bash
twag init
twag doctor
```

### Step 5: Set LLM API key

```bash
export GEMINI_API_KEY="..."  # Required
export ANTHROPIC_API_KEY="..."  # Optional, for enrichment
export DEEPSEEK_API_KEY="..."  # Optional, for DeepSeek text models
```

## Quick Reference

```bash
# Full pipeline
twag fetch && twag process && twag digest

# Browse high-signal tweets
twag search --today -s 7

# Rich JSON for digest/agent consumption
twag search --time 2h -s 6 -f json -n 50

# Check stats
twag stats --today
```

## Common Workflows

### Morning market check

```bash
twag fetch && twag process
twag search --today -s 7
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
twag analyze 123456789 --thread --replies \
  --reply-depth 2 --max-reply-nodes 25 --max-pages 5
```

Analyze is target-only by default. `--thread` persists the full Bird thread, and `--replies` persists a bounded
breadth-first reply tree (`--reply-depth 1` is direct replies only). When both are enabled, every fetched thread status
can seed reply traversal. `--max-reply-nodes` caps both stored reply statuses and visited reply-source nodes;
`--max-pages` caps each Bird request, while omitting it requests all available pages. Thread/reply context keeps the
normal link, media, X Article, reply relationship, and conversation metadata, but only the target is classified and
printed. Explicit context-fetch failures return nonzero so extraction workflows cannot mistake partial context for a
complete fetch.

## Commands

### Search (most common)

```bash
# Browse mode (no query) — uses rich FeedTweet data
twag search --today -s 7             # High-signal tweets since market close
twag search --time 2h -s 6 -f json -n 50  # Rich JSON for digests
twag search -c fed_policy --time 7d  # Browse by category

# Full-text search mode
twag search "query"                  # FTS5 search
twag search "query" --live           # Fresh public X results through bird
twag search "query" --cached         # Explicit local-only search (default)
twag search "query" -c fed_policy    # Filter by category
twag search "query" -a handle        # Filter by author
twag search "query" --ticker AAPL    # Filter by ticker
twag search "query" --today          # Since last market close
twag search "query" --time 7d        # Last N days
twag search "query" -s 7             # Min score threshold
twag search "query" --format full    # Digest-style output
twag search "query" --format json    # JSON output
twag search --bookmarks              # Only bookmarked tweets
twag search "query" --tier 1         # Filter by signal tier
twag search "query" --order score    # Sort: rank, score, or time
```

**Query syntax:**
- Simple: `inflation fed` (matches both)
- Phrase: `"rate hike"` (exact)
- Boolean: `inflation AND fed`, `fed NOT fomc`
- Prefix: `infla*` (wildcard)
- Cashtag: `twag search '$BLND OR "Blend Labs"' --live` (single quotes preserve `$BLND`)

Query searches are local-only by default. `--live` queries fresh public X
results through authenticated `bird search`, stores the in-window result set,
and limits output to those fetched IDs. New live rows are classified when score,
category, tier, ticker, or score-order filters need model metadata. Bird is
bounded to 30 seconds; classification defaults to a killable 120-second overall
timeout. Live syntax supports X terms, phrases, `OR`, and cashtags; FTS prefixes
and column expressions are cache-only.

### Fetch & Process

```bash
twag fetch                    # Home + tier-1 + bookmarks
twag fetch --no-tier1         # Home only
twag fetch --source user -u @handle  # Specific user
twag fetch --source search -q "query"  # Search tweets
twag fetch --stagger 5        # Rotate: fetch 5 least-recent tier-1
twag fetch --delay 5.0        # Pacing between tier-1 fetches (default: 3s)

twag process                  # Score unprocessed (no alerts by default)
twag process -n 100           # Limit batch
twag process --dry-run        # Preview
twag process --notify         # Send alerts
twag process --no-reprocess-quotes     # Skip reprocessing dependency tweets
twag process --reprocess-min-score 5   # Min score for reprocessing (default: 3)

twag spine emit              # Append eligible signal-event v1 records
twag eval run                # Run the versioned scoring golden set
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
twag accounts demote @handle  # Demote to tier-2
twag accounts mute @handle    # Mute account
twag accounts boost @handle --amount 10
twag accounts decay           # Apply daily decay
twag accounts import          # Import from following.txt
```

### Stats & Maintenance

```bash
twag stats                    # All-time
twag stats --today            # Today
twag inference usage          # LLM token/cost report for last 30 days
twag inference usage --all-time  # Include all logged inference usage
twag prune --days 14          # Delete old tweets
twag export --days 7          # Export recent
```

### Narratives

```bash
twag narratives list          # List active narratives
```

### Database

```bash
twag db path                  # Show location
twag db shell                 # SQLite shell
twag db init                  # Initialize/reset database
twag db rebuild-fts           # Rebuild search index
twag db dump                  # Backup
twag db dump --stdout         # Backup to stdout
twag db restore backup.sql    # Restore
twag db restore backup.sql --force  # Restore without confirmation
```

### Web UI

```bash
twag web                      # Start (localhost:5173)
twag web --host 127.0.0.1     # Localhost only
twag web --port 8080          # Custom port
twag web --dev                # Dev mode (Vite + HMR)
twag web --no-reload          # Disable auto-reload
```

### Config

```bash
twag config show              # Show config
twag config path              # Show path
twag config set key value     # Update setting
twag config set scoring.min_score_for_analysis 6
```

## Scoring Tiers

| Score | Level | Behavior |
|-------|-------|----------|
| 8-10 | Alert | Real-time alert |
| 7 | High signal | Enriched, in digests |
| 5-6 | Market relevant | In digests |
| 3-4 | News/context | Searchable |
| 0-2 | Noise | Filtered out |

## Categories

The coarse filter taxonomy is single-sourced in `twag/taxonomy.py`.

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `AUTH_TOKEN` | Yes | Twitter auth cookie |
| `CT0` | Yes | Twitter ct0 cookie |
| `GEMINI_API_KEY` | Yes | Gemini triage/vision |
| `DEEPSEEK_API_KEY` | No | DeepSeek text triage/enrichment |
| `ANTHROPIC_API_KEY` | No | Anthropic enrichment |
| `TELEGRAM_BOT_TOKEN` | No | Alerts |
| `TELEGRAM_CHAT_ID` | No | Alert destination |

## Digest interpretation (JSON from twag search)
Read /home/clifton/clawd/MARKET_SUMMARY_FORMAT.md and follow it exactly; it is the single house style.
Two tiers: full bullets for score >= 6. Tweets scoring 5 get at most a final "ALSO NOTED" section of one-line bullets, max 6 lines; skip it entirely if thin.
If any tweet has catalyst_status "resolved" touching an owned or watchlist instrument, lead the digest with a one-line ⚠️ RESOLVED flag for it.
If a tweet was already alerted in real time, still include it — the digest is the record.

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
