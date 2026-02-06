# twag 📊

Twitter/X market-signal aggregation with LLM-powered triage, enrichment, and digest generation.

**twag** pulls tweets from your timeline, scores them for market relevance using LLMs, enriches high-signal content, and generates daily digests. It's designed for traders and investors who want signal without the noise.

## Features

- **Smart Scoring** — LLM-powered triage (0-10) with category tagging
- **Full-Text Search** — SQLite FTS5 with boolean queries and filters
- **X Article Summaries** — Extracts key points and action items from long-form posts
- **Telegram Alerts** — Real-time notifications for high-signal tweets
- **Web Feed** — FastAPI + React UI for browsing processed tweets
- **OpenClaw Skill** — Native integration with [OpenClaw](https://github.com/openclaw/openclaw) agents

## Prerequisites

### bird CLI (Required)

twag uses [bird](https://github.com/steipete/bird) to access Twitter/X. Install it first:

```bash
# npm (recommended)
npm install -g @steipete/bird

# or pnpm/bun
pnpm add -g @steipete/bird
bun add -g @steipete/bird

# or Homebrew (macOS)
brew install steipete/tap/bird
```

Verify installation:

```bash
bird --version
```

### Twitter Authentication

bird uses cookie-based auth. You need two cookies from your browser:

1. **AUTH_TOKEN** — Your `auth_token` cookie
2. **CT0** — Your `ct0` cookie

#### Getting Your Cookies

1. Log into [x.com](https://x.com) in your browser
2. Open DevTools (F12) → Application → Cookies → `https://x.com`
3. Copy the values of `auth_token` and `ct0`

Set them as environment variables:

```bash
export AUTH_TOKEN="your_auth_token_here"
export CT0="your_ct0_here"
```

Or add to `~/.env` (twag will source this automatically):

```bash
echo 'export AUTH_TOKEN="..."' >> ~/.env
echo 'export CT0="..."' >> ~/.env
```

Verify auth works:

```bash
bird whoami
```

### LLM API Keys

**Required:**
- `GEMINI_API_KEY` — [Google AI Studio](https://aistudio.google.com/apikey) (free tier available)

**Optional:**
- `ANTHROPIC_API_KEY` — For higher-quality enrichment on high-signal tweets

```bash
export GEMINI_API_KEY="your_gemini_key"
export ANTHROPIC_API_KEY="your_anthropic_key"  # optional
```

## Installation

### From PyPI (Recommended)

```bash
pip install twag
```

### From Source

```bash
git clone https://github.com/clifton/twag.git
cd twag
pip install -e .
```

### Using uv

```bash
uv pip install twag
# or from source
uv pip install -e .
```

## Quick Start

```bash
# 1. Initialize config and database
twag init

# 2. Verify dependencies and environment
twag doctor

# 3. Fetch tweets from your timeline
twag fetch

# 4. Score and process tweets
twag process

# 5. Generate today's digest
twag digest --stdout

# 6. Search for specific topics
twag search "fed rate" --today
```

## Core Workflow

```
FETCH → PROCESS → DIGEST
```

1. **Fetch** — Pull tweets from home timeline, tier-1 accounts, bookmarks
2. **Process** — Score tweets with LLM, categorize, enrich high-signal content
3. **Digest** — Generate markdown summaries grouped by theme

## CLI Reference

### Setup Commands

```bash
twag init              # Initialize config and database
twag init --force      # Reinitialize (destructive)
twag doctor            # Check dependencies and environment
```

### Fetch Commands

```bash
# Default: home timeline + tier-1 accounts + bookmarks
twag fetch

# Single tweet (ID or URL)
twag fetch 1234567890123456789
twag fetch https://x.com/user/status/1234567890123456789

# User timeline
twag fetch --source user --handle @NickTimiraos --count 50

# Search
twag fetch --source search --query "Fed Powell rate" --count 30

# Control sources
twag fetch --no-tier1 --no-bookmarks
```

### Process Commands

```bash
twag process                    # Process unscored tweets
twag process --limit 100        # Limit batch size
twag process --dry-run          # Preview only
twag process --no-notify        # Skip Telegram alerts

# Process specific tweet
twag process 1234567890123456789
```

### Search Commands

```bash
# Basic search
twag search "inflation fed"

# With filters
twag search "rate hike" --category fed_policy
twag search "NVDA" --author zerohedge
twag search "earnings" --ticker AAPL

# Time filters
twag search "breaking" --today              # Since last market close
twag search "fed" --time 7d                 # Last 7 days
twag search "macro" --since 2026-01-15      # From specific date

# Output formats
twag search "fed" --format brief            # Compact output
twag search "fed" --format full             # Digest-style
twag search "fed" --format json             # JSON output

# Score threshold
twag search "market" --min-score 7          # High-signal only
```

**Query syntax:**
- Simple: `inflation fed` (matches both)
- Phrase: `"rate hike"` (exact match)
- Boolean: `inflation AND fed`, `fed NOT fomc`
- Prefix: `infla*` (wildcard)

### Digest Commands

```bash
twag digest                     # Generate today's digest
twag digest --date 2026-02-06   # Specific date
twag digest --stdout            # Output to terminal
twag digest --min-score 6       # Custom threshold
```

### Account Management

```bash
twag accounts list              # All tracked accounts
twag accounts list --tier 1     # Tier-1 only
twag accounts add @handle       # Add account
twag accounts add @handle -t 1  # Add as tier-1
twag accounts promote @handle   # Promote to tier-1
twag accounts demote @handle    # Demote to tier-2
twag accounts mute @handle      # Mute account
twag accounts boost @handle --amount 10  # Boost weight
twag accounts decay             # Apply daily decay
twag accounts import            # Import from following.txt
```

### Stats & Maintenance

```bash
twag stats                      # All-time stats
twag stats --today              # Today's stats

twag prune --days 14            # Delete old tweets
twag prune --dry-run            # Preview prune

twag export --days 7            # Export recent data
```

### Database Commands

```bash
twag db path                    # Show database location
twag db shell                   # Open SQLite shell
twag db rebuild-fts             # Rebuild search index
twag db dump                    # Backup database
twag db restore backup.sql      # Restore from backup
```

### Web Interface

```bash
twag web                        # Start web UI (localhost:5173)
twag web --host 127.0.0.1       # Bind to localhost only
twag web --port 8080            # Custom port
twag web --dev                  # Dev mode (Vite + hot reload)
```

⚠️ **Security:** The web interface has no authentication. Only run on trusted networks or bind to localhost.

### Configuration

```bash
twag config show                # Show current config
twag config path                # Show config file path
twag config set llm.triage_model gemini-2.0-flash
twag config set scoring.alert_threshold 8
```

## Data Paths

twag follows XDG defaults:

| Path | Purpose |
|------|---------|
| `~/.config/twag/config.json` | Configuration |
| `~/.local/share/twag/twag.db` | SQLite database |
| `~/.local/share/twag/digests/` | Generated digests |
| `~/.local/share/twag/following.txt` | Followed accounts |

Override with `TWAG_DATA_DIR` environment variable.

## Scoring System

Tweets are scored 0-10:

| Score | Signal Level | Behavior |
|-------|--------------|----------|
| 8-10 | High signal | Telegram alert (if configured) |
| 6-7 | Market relevant | Included in digests |
| 4-5 | News/context | Searchable, not in digests |
| 0-3 | Noise | Stored but filtered out |

### Categories

`fed_policy`, `inflation`, `job_market`, `macro_data`, `earnings`, `equities`, `rates_fx`, `credit`, `banks`, `consumer_spending`, `commodities`, `energy`, `geopolitical`, `tech_business`, `ai_advancement`, `crypto`

## Automation

### Data Collection (systemd timer)

Create `~/.config/systemd/user/twag-aggregator.service`:

```ini
[Unit]
Description=TWAG Twitter Aggregator
After=network.target

[Service]
Type=oneshot
ExecStart=%h/.local/bin/twag fetch && %h/.local/bin/twag process
WorkingDirectory=%h
EnvironmentFile=%h/.env
```

Create `~/.config/systemd/user/twag-aggregator.timer`:

```ini
[Unit]
Description=Run TWAG every 15 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:

```bash
systemctl --user daemon-reload
systemctl --user enable --now twag-aggregator.timer
```

### macOS (launchd)

See [SUGGESTED_CRON_SCHEDULE.md](./SUGGESTED_CRON_SCHEDULE.md) for launchd plist examples.

### Telegram Alerts

1. Create a bot via [@BotFather](https://t.me/botfather)
2. Get your chat ID by messaging the bot
3. Set environment variables:

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

Tweets scoring 8+ will trigger alerts automatically during `twag process`.

## OpenClaw Integration

twag is an [OpenClaw](https://github.com/openclaw/openclaw) skill. Once installed, agents can:

```bash
# Search for market-relevant tweets
twag search "fed rate" --today -s 7

# Generate digests
twag digest --stdout

# Analyze specific tweets
twag analyze https://x.com/user/status/123
```

### Skill Installation

The skill is auto-discovered if twag is in PATH. For manual setup:

```bash
# Link skill to OpenClaw
ln -s /path/to/twag ~/.openclaw/skills/twag
```

### Scheduled Digests

See [SUGGESTED_CRON_SCHEDULE.md](./SUGGESTED_CRON_SCHEDULE.md) for OpenClaw cron job examples that deliver digests to Telegram.

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `AUTH_TOKEN` | Yes | Twitter auth cookie |
| `CT0` | Yes | Twitter ct0 cookie |
| `GEMINI_API_KEY` | Yes | LLM triage/vision |
| `ANTHROPIC_API_KEY` | No | Enhanced enrichment |
| `TELEGRAM_BOT_TOKEN` | No | Alert delivery |
| `TELEGRAM_CHAT_ID` | No | Alert destination |
| `TWAG_DATA_DIR` | No | Override data directory |

## Troubleshooting

### "bird not found"

```bash
# Check if bird is installed
which bird

# Install if missing
npm install -g @steipete/bird
```

### "Authentication failed" / 401 errors

```bash
# Verify cookies are set
echo $AUTH_TOKEN
echo $CT0

# Test bird auth
bird whoami

# If expired, get fresh cookies from browser
```

### "Query IDs stale" / 404 errors

```bash
# Refresh GraphQL query cache
bird query-ids --fresh
```

### "GEMINI_API_KEY not set"

```bash
# Verify key is exported
echo $GEMINI_API_KEY

# Test with curl
curl "https://generativelanguage.googleapis.com/v1/models?key=$GEMINI_API_KEY"
```

### Database issues

```bash
# Check database location
twag db path

# Rebuild search index
twag db rebuild-fts

# Backup and restore
twag db dump backup.sql
twag db restore backup.sql --force
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint and format
ruff check .
ruff format .

# Frontend development
cd twag/web/frontend
npm install
npm run dev
```

## License

MIT. See [LICENSE](./LICENSE).

## Links

- **Repository:** https://github.com/clifton/twag
- **Issues:** https://github.com/clifton/twag/issues
- **bird CLI:** https://github.com/steipete/bird
- **OpenClaw:** https://github.com/openclaw/openclaw
