# twag Installation Guide

Step-by-step instructions for installing twag and its dependencies.

## Prerequisites

- Python 3.10+ with pip
- Node.js 18+ with npm (for bird CLI)
- A Twitter/X account

## Step 1: Install bird CLI

bird provides Twitter/X API access. Choose one method:

### npm (Recommended)

```bash
npm install -g @steipete/bird
```

### Homebrew (macOS)

```bash
brew install steipete/tap/bird
```

### pnpm/bun

```bash
pnpm add -g @steipete/bird
# or
bun add -g @steipete/bird
```

**Verify:**

```bash
bird --version
# Should output: 0.8.0 or similar
```

## Step 2: Get Twitter Cookies

bird uses cookie-based authentication. You need two cookies from your browser:

1. Open [x.com](https://x.com) and log in
2. Open DevTools: `F12` (or `Cmd+Option+I` on macOS)
3. Go to **Application** → **Cookies** → `https://x.com`
4. Find and copy:
   - `auth_token` — a long alphanumeric string
   - `ct0` — another long alphanumeric string

## Step 3: Set Environment Variables

Add to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
export AUTH_TOKEN="your_auth_token_here"
export CT0="your_ct0_here"
```

Or create `~/.env`:

```bash
# ~/.env
export AUTH_TOKEN="your_auth_token_here"
export CT0="your_ct0_here"
```

**Verify auth works:**

```bash
source ~/.env  # if using .env file
bird whoami
# Should show your Twitter username
```

## Step 4: Get LLM API Keys

### Gemini (Required)

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Create an API key
3. Add to environment:

```bash
export GEMINI_API_KEY="your_gemini_key"
```

### Anthropic (Optional)

For higher-quality tweet enrichment:

1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Create an API key
3. Add to environment:

```bash
export ANTHROPIC_API_KEY="your_anthropic_key"
```

## Step 5: Install twag

### From PyPI

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
```

## Step 6: Initialize

```bash
# Create config and database
twag init

# Verify everything works
twag doctor
```

`twag doctor` checks:
- bird is installed and in PATH
- Twitter auth is valid
- LLM API keys are set
- Database is accessible

## Step 7: Test

```bash
# Fetch some tweets
twag fetch --no-tier1

# Process them
twag process --limit 10

# Search
twag search "market" --today

# Check stats
twag stats --today
```

## Optional: Telegram Alerts

To receive alerts for high-signal tweets:

### Create a Telegram Bot

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot` and follow prompts
3. Save the bot token

### Get Your Chat ID

1. Message your new bot
2. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Find `"chat":{"id":123456789}` — that's your chat ID

### Set Environment Variables

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

Now tweets scoring 8+ will trigger Telegram alerts during `twag process`.

## Optional: Automation

### systemd (Linux)

Create `~/.config/systemd/user/twag.service`:

```ini
[Unit]
Description=TWAG Twitter Aggregator

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'source ~/.env && twag fetch && twag process'
```

Create `~/.config/systemd/user/twag.timer`:

```ini
[Unit]
Description=Run TWAG every 15 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
```

Enable:

```bash
systemctl --user daemon-reload
systemctl --user enable --now twag.timer
```

### launchd (macOS)

See [SUGGESTED_CRON_SCHEDULE.md](./SUGGESTED_CRON_SCHEDULE.md) for plist examples.

## Troubleshooting

### "command not found: bird"

bird isn't in PATH. Try:

```bash
# Check npm global bin location
npm bin -g

# Add to PATH if needed
export PATH="$(npm bin -g):$PATH"
```

### "Unauthorized" / 401 errors

Your cookies expired. Get fresh ones from the browser (Step 2).

### "Query IDs stale" / 404 errors

Twitter changed their GraphQL endpoints:

```bash
bird query-ids --fresh
```

### "GEMINI_API_KEY not set"

Ensure the variable is exported:

```bash
echo $GEMINI_API_KEY  # Should print your key

# If empty, source your env file
source ~/.env
```

### Database errors

```bash
# Check database exists
twag db path

# Rebuild if corrupted
twag init --force  # WARNING: This resets the database
```

## Complete ~/.env Example

```bash
# Twitter auth (from browser cookies)
export AUTH_TOKEN="abc123..."
export CT0="def456..."

# LLM APIs
export GEMINI_API_KEY="AIza..."
export ANTHROPIC_API_KEY="sk-ant-..."  # optional

# Telegram alerts (optional)
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="987654321"
```

## Next Steps

1. Run `twag fetch && twag process` to populate your database
2. Use `twag search` to find relevant tweets
3. Set up automation for continuous data collection
4. Configure OpenClaw cron jobs for scheduled digests

See [README.md](./README.md) for full CLI reference.
