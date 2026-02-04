# twag - Twitter Aggregator

A CLI tool for aggregating and curating market-relevant Twitter/X content. Uses LLM-powered scoring to filter signal from noise.

## Installation

```bash
# Install from PyPI (when published)
pip install twag

# Or install from source
pip install git+https://github.com/clifton/twag.git

# Or local development install
git clone https://github.com/clifton/twag.git
cd twag
pip install -e .
```

## Quick Start

```bash
# 1. Initialize twag (creates dirs, config, database)
twag init

# 2. Check dependencies
twag doctor

# 3. Set environment variables (add to ~/.bashrc or ~/.env)
export GEMINI_API_KEY="your-key"
export AUTH_TOKEN="your-twitter-auth-token"
export CT0="your-twitter-ct0"

# 4. Add accounts to track
twag accounts add @NickTimiraos --tier 1
twag accounts add @zerohedge --tier 1

# 5. Fetch, process, and generate digest
twag fetch && twag process && twag digest
```

## Prerequisites

- Python 3.10+
- `bird` CLI installed and configured with Twitter auth
- `GEMINI_API_KEY` environment variable (for triage/vision)
- `ANTHROPIC_API_KEY` environment variable (optional, for enrichment)
- Twitter auth tokens: `AUTH_TOKEN`, `CT0`

## Data Locations

twag follows the [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html):

| Data | Default Location | Override |
|------|------------------|----------|
| Config | `~/.config/twag/config.json` | `XDG_CONFIG_HOME` |
| Database | `~/.local/share/twag/twag.db` | `TWAG_DATA_DIR` |
| Digests | `~/.local/share/twag/digests/` | `TWAG_DATA_DIR` |
| Following | `~/.local/share/twag/following.txt` | `TWAG_DATA_DIR` |

### Custom Data Directory

Set `TWAG_DATA_DIR` to use a custom location:

```bash
export TWAG_DATA_DIR=/path/to/my/data
twag fetch  # Uses /path/to/my/data/twag.db, etc.
```

Or configure in `~/.config/twag/config.json`:

```json
{
  "paths": {
    "data_dir": "/path/to/my/data"
  }
}
```

### Migration from Old Location

If migrating from an existing workspace:

```bash
./scripts/migrate.sh /old/path/to/twitter-feed
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FETCH PHASE                              │
│  bird CLI → Parse tweets → Dedupe against SQLite → Store        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        PROCESS PHASE                             │
│  Batch triage (Gemini Flash) → Score 0-10 → Expand high-signal  │
│  → Enrich (Claude) → Update account stats                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        DIGEST PHASE                              │
│  Query by date → Group by tier → Render markdown                │
└─────────────────────────────────────────────────────────────────┘
```

## CLI Reference

### Setup Commands

```bash
# Initialize twag (run once after install)
twag init
twag init --force  # Overwrite existing config

# Check dependencies and configuration
twag doctor
```

### Fetch Commands

```bash
# Fetch home timeline + tier-1 accounts
twag fetch

# Fetch home only (no tier-1)
twag fetch --no-tier1

# Fetch specific user
twag fetch --source user -u @NickTimiraos -n 50

# Search tweets
twag fetch --source search -q "Fed Powell rate" -n 30
```

### Process Commands

```bash
# Process unscored tweets
twag process

# Process with limit
twag process -n 100

# Dry run (preview only)
twag process --dry-run

# Override model
twag process -m claude-opus-4-20250514

# Disable Telegram alerts
twag process --no-notify
```

### Digest Commands

```bash
# Generate today's digest
twag digest

# Generate for specific date
twag digest -d 2026-01-29

# Output to stdout
twag digest --stdout

# Custom minimum score
twag digest --min-score 6
```

### Account Commands

```bash
# List all accounts
twag accounts list

# List tier-1 only
twag accounts list -t 1

# Include muted
twag accounts list --muted

# Add account
twag accounts add @NickTimiraos

# Add as tier-1
twag accounts add @DeItaone -t 1

# Promote to tier-1
twag accounts promote @handle

# Mute account
twag accounts mute @handle

# Apply daily decay
twag accounts decay

# Boost account weight
twag accounts boost @handle --amount 10

# Import from following.txt
twag accounts import
```

### Search Commands

```bash
# Basic full-text search
twag search "inflation fed"

# Search with filters
twag search "rate hike" -c fed_policy -s 7
twag search "NVDA" -a zerohedge --time 7d
twag search "earnings" --ticker AAPL --today

# Bookmarked tweets only
twag search "macro" --bookmarks

# Output formats
twag search "fed" --format brief   # default: one-liner per result
twag search "fed" --format full    # digest-style with full content
twag search "fed" --format json    # JSON output
```

**Query syntax:**
- Simple terms: `inflation fed` (matches both)
- Phrases: `"rate hike"` (exact match)
- Boolean: `inflation AND fed`, `fed NOT fomc`
- Prefix: `infla*` (wildcard)
- Column filter: `author_handle:zerohedge`

**Filter options:**
- `--category, -c`: Filter by category (fed_policy, equities, etc.)
- `--author, -a`: Filter by author handle
- `--min-score, -s`: Minimum relevance score
- `--ticker, -T`: Filter by ticker symbol
- `--bookmarks, -b`: Only bookmarked tweets

**Time filters:**
- `--since`: Start time (YYYY-MM-DD or relative like 1d, 7d)
- `--until`: End time (YYYY-MM-DD)
- `--today`: Since previous market close (4pm ET)
- `--time`: Time range shorthand (today, 7d, 2025-01-15, etc.)

### Narrative Commands

```bash
# List active narratives
twag narratives list
```

### Stats & Maintenance

```bash
# Show all-time stats
twag stats

# Show today's stats
twag stats --today

# Show specific date
twag stats -d 2026-01-29

# Prune old tweets
twag prune --days 14

# Preview prune
twag prune --days 14 --dry-run

# Export recent data
twag export --days 7
```

### Config Commands

```bash
# Show config
twag config show

# Show config path
twag config path

# Set value
twag config set llm.triage_model gemini-3-flash-preview
twag config set scoring.alert_threshold 9
twag config set paths.data_dir /custom/path
```

### Database Commands

```bash
# Show database path
twag db path

# Open SQLite shell
twag db shell

# Initialize database
twag db init

# Migrate from seen.json
twag db migrate-seen

# Rebuild FTS5 search index
twag db rebuild-fts
```

### Web Interface

```bash
# Start web interface
twag web

# Custom host/port
twag web --host 0.0.0.0 --port 8080
```

## Account Tiers

- **Tier 1 (Core)**: High-value accounts fetched individually every cycle
- **Tier 2 (Followed)**: Accounts from following.txt, caught via home timeline
- **Tier 3 (Discovered)**: Auto-discovered accounts with good signal

## Scoring System

| Score | Tier | Description |
|-------|------|-------------|
| 8-10 | High Signal | Actionable insights, triggers Telegram alert |
| 6-7 | Market Relevant | Worth including in digest |
| 4-5 | News | Context, included if space allows |
| 0-3 | Noise | Filtered out |

## Categories

- `fed_policy` - Fed/central bank policy
- `inflation` - Inflation data and expectations
- `job_market` - Employment and labor data
- `macro_data` - Economic data releases
- `earnings` - Company earnings
- `equities` - Stock analysis
- `rates_fx` - Rates and FX
- `credit` - Credit markets and spreads
- `banks` - Banking sector news
- `consumer_spending` - Consumer spending trends
- `capex` - Capital expenditure and investment
- `commodities` - Commodities (general)
- `energy` - Energy markets (oil, gas, etc.)
- `metals_mining` - Metals and mining
- `geopolitical` - Geopolitics affecting markets
- `sanctions` - Sanctions and trade restrictions
- `tech_business` - Tech business news
- `ai_advancement` - AI developments and implications
- `crypto` - Cryptocurrency
- `noise` - Not market relevant

## Cron Setup

```bash
# Morning full cycle (7 AM)
0 7 * * * /path/to/cron-runner.sh full

# Daytime fetch-only (every 30 min, 7am-10pm)
*/30 7-22 * * * /path/to/cron-runner.sh fetch-only
```

Or using the installed script:

```bash
# Copy to local bin
cp scripts/cron-runner.sh ~/.local/bin/twag-cron
chmod +x ~/.local/bin/twag-cron

# Add to crontab
0 7 * * * ~/.local/bin/twag-cron full
*/30 7-22 * * * ~/.local/bin/twag-cron fetch-only
```

## Configuration

Default config in `~/.config/twag/config.json`:

```json
{
  "llm": {
    "triage_model": "gemini-3-flash-preview",
    "triage_provider": "gemini",
    "enrichment_model": "claude-opus-4-5-20251101",
    "enrichment_provider": "anthropic",
    "vision_model": "gemini-3-flash-preview",
    "vision_provider": "gemini"
  },
  "scoring": {
    "min_score_for_digest": 5,
    "high_signal_threshold": 7,
    "alert_threshold": 8,
    "batch_size": 15
  },
  "notifications": {
    "telegram_enabled": true,
    "quiet_hours_start": 23,
    "quiet_hours_end": 8,
    "max_alerts_per_hour": 10
  },
  "accounts": {
    "decay_rate": 0.05,
    "boost_increment": 5,
    "auto_promote_threshold": 75
  },
  "paths": {
    "data_dir": null
  }
}
```

## Telegram Notifications

High-signal tweets (score >= 8) trigger real-time Telegram alerts.

Required environment variables:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Or set in config:
```bash
twag config set notifications.telegram_chat_id YOUR_CHAT_ID
```

## License

MIT License - see [LICENSE](LICENSE) for details.
