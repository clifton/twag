---
name: twag
description: Twitter/X aggregator for market-relevant signals. Use when processing twitter feed, managing followed accounts, searching tweets, or generating daily digests.
---

# twag - Twitter Aggregator Skill

Clawdbot skill wrapper for twag - a CLI tool that aggregates and curates market-relevant Twitter content using LLM-powered scoring.

## Installation

```bash
# Install twag
pip install twag

# Or install from source
pip install git+https://github.com/clifton/twag.git

# Initialize (creates data dirs, config, database)
twag init

# Verify installation
twag doctor
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google Gemini API key for triage/vision |
| `ANTHROPIC_API_KEY` | No | Anthropic API key for enrichment (optional) |
| `AUTH_TOKEN` | Yes | Twitter auth token (from browser cookies) |
| `CT0` | Yes | Twitter CT0 token (from browser cookies) |
| `TWAG_DATA_DIR` | No | Override data directory (default: `~/.local/share/twag/`) |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token for alerts |
| `TELEGRAM_CHAT_ID` | No | Telegram chat ID for alerts |

## Using with Clawdbot

To use twag data in a clawdbot workspace, set `TWAG_DATA_DIR` to point to the workspace:

```bash
# In clawdbot config or skill environment
export TWAG_DATA_DIR=/path/to/clawdbot/workspace/memory/twitter-feed
```

Or configure in `~/.config/twag/config.json`:

```json
{
  "paths": {
    "data_dir": "/path/to/clawdbot/workspace/memory/twitter-feed"
  }
}
```

## Quick Reference

```bash
# Fetch and process new tweets
twag fetch && twag process && twag digest

# Check what's new
twag stats --today

# Search for market signals
twag search "fed rate" --today
twag search "earnings" --ticker NVDA -s 7

# Account management
twag accounts list
twag accounts add @handle --tier 1
```

## What's Moving Markets?

```bash
# Since market close
twag search "market" --today -s 7

# Fed/macro
twag search "fed rate" -c fed_policy --today
twag search "inflation CPI" --today

# Specific tickers
twag search "earnings" --ticker NVDA
twag search "guidance" --ticker AAPL --today

# High-signal only
twag search "breaking" --today -s 8

# By author
twag search "fed" -a NickTimiraos --time 7d
```

## Categories

`fed_policy`, `inflation`, `job_market`, `macro_data`, `earnings`, `equities`, `rates_fx`, `credit`, `banks`, `consumer_spending`, `commodities`, `energy`, `geopolitical`, `tech_business`, `ai_advancement`, `crypto`

## Data Locations

Default XDG paths:
- Config: `~/.config/twag/config.json`
- Database: `~/.local/share/twag/twag.db`
- Digests: `~/.local/share/twag/digests/`
- Following: `~/.local/share/twag/following.txt`

Override with `TWAG_DATA_DIR` or `paths.data_dir` in config.

## Full Documentation

See the [twag README](https://github.com/clifton/twag) for complete CLI documentation.
