# Automated Scheduling for twag

This guide covers two layers of automation:

1. **Data Collection** — Frequent fetch/process cycle (every 15 min)
2. **Digest Delivery** — Telegram summaries at key market times

## Data Collection

### Linux (systemd)

**~/.config/systemd/user/twag-aggregator.service**

```ini
[Unit]
Description=TWAG Twitter Aggregator
After=network.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'source ~/.env && twag fetch && twag process'
WorkingDirectory=%h

[Install]
WantedBy=default.target
```

**~/.config/systemd/user/twag-aggregator.timer**

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

**Enable:**

```bash
systemctl --user daemon-reload
systemctl --user enable --now twag-aggregator.timer

# Check status
systemctl --user status twag-aggregator.timer
systemctl --user list-timers
journalctl --user -u twag-aggregator.service -f  # Watch logs
```

### macOS (launchd)

**~/Library/LaunchAgents/com.twag.aggregator.plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.twag.aggregator</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>source ~/.env && twag fetch && twag process</string>
    </array>
    <key>StartInterval</key>
    <integer>900</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/twag-aggregator.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/twag-aggregator.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

**Load:**

```bash
launchctl load ~/Library/LaunchAgents/com.twag.aggregator.plist

# Check status
launchctl list | grep twag

# View logs
tail -f /tmp/twag-aggregator.log
```

### Using the cron-runner.sh Script

The repo includes a helper script at `scripts/cron-runner.sh`:

```bash
# Full cycle: fetch, process, digest, decay, prune
./scripts/cron-runner.sh full

# Quick fetch only (no tier-1 to reduce API calls)
./scripts/cron-runner.sh fetch-only

# Process only
./scripts/cron-runner.sh process-only

# Digest only
./scripts/cron-runner.sh digest-only
```

The script:
- Sources `~/.env` automatically
- Ensures PATH includes common install locations
- Logs with timestamps

## Telegram Digest Delivery

For OpenClaw users, add these cron jobs to deliver formatted digests to Telegram.

### Setup

1. Create a Telegram bot via [@BotFather](https://t.me/botfather)
2. Set `TELEGRAM_BOT_TOKEN` in your environment
3. Get your chat ID by messaging the bot and checking:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Replace `YOUR_CHAT_ID` in the jobs below

### OpenClaw Cron Jobs

Add to your OpenClaw cron configuration:

```json
{
  "jobs": [
    {
      "name": "twag morning digest",
      "schedule": {
        "kind": "cron",
        "expr": "0 7 * * 1-5",
        "tz": "America/Chicago"
      },
      "sessionTarget": "isolated",
      "payload": {
        "kind": "agentTurn",
        "message": "Generate an overnight tweet digest. Run: twag search --time 10h -s 6 -f full. Group tweets by theme, condense into bullets, format per TELEGRAM_DIGEST_FORMAT.md. Use [🔗](url) for citations, [📊](url) for charts. If nothing notable, reply NO_REPLY."
      },
      "delivery": {
        "mode": "announce",
        "channel": "telegram",
        "to": "YOUR_CHAT_ID"
      },
      "enabled": true
    },
    {
      "name": "twag 2-hour digest",
      "schedule": {
        "kind": "cron",
        "expr": "0 9,11,13,15,17,19,21 * * 1-5",
        "tz": "America/Chicago"
      },
      "sessionTarget": "isolated",
      "payload": {
        "kind": "agentTurn",
        "message": "Generate a 2-hour tweet digest. Run: twag search --time 2h -s 6 -f full. Group by theme, condense into bullets, format per TELEGRAM_DIGEST_FORMAT.md. Use [🔗](url) for citations, [📊](url) for charts. If nothing notable, reply NO_REPLY."
      },
      "delivery": {
        "mode": "announce",
        "channel": "telegram",
        "to": "YOUR_CHAT_ID"
      },
      "enabled": true
    },
    {
      "name": "twag weekend digest",
      "schedule": {
        "kind": "cron",
        "expr": "0 15 * * 0",
        "tz": "America/Chicago"
      },
      "sessionTarget": "isolated",
      "payload": {
        "kind": "agentTurn",
        "message": "Generate a weekend tweet digest covering Friday night through Sunday afternoon. Run: twag search --time 42h -s 6 -f full. Group tweets by theme, condense into bullets, format per TELEGRAM_DIGEST_FORMAT.md. Use [🔗](url) for citations, [📊](url) for charts. If nothing notable, reply NO_REPLY."
      },
      "delivery": {
        "mode": "announce",
        "channel": "telegram",
        "to": "YOUR_CHAT_ID"
      },
      "enabled": true
    },
    {
      "name": "twag sunday night digest",
      "schedule": {
        "kind": "cron",
        "expr": "0 21 * * 0",
        "tz": "America/Chicago"
      },
      "sessionTarget": "isolated",
      "payload": {
        "kind": "agentTurn",
        "message": "Generate a Sunday evening tweet digest for pre-market prep. Run: twag search --time 6h -s 6 -f full. Group by theme, condense into bullets, format per TELEGRAM_DIGEST_FORMAT.md. Use [🔗](url) for citations, [📊](url) for charts. If nothing notable, reply NO_REPLY."
      },
      "delivery": {
        "mode": "announce",
        "channel": "telegram",
        "to": "YOUR_CHAT_ID"
      },
      "enabled": true
    }
  ]
}
```

### Schedule Summary

| Job | Schedule | Lookback | Purpose |
|-----|----------|----------|---------|
| Morning | 7am Mon-Fri | 10 hours | Overnight summary |
| 2-hour | 9am-9pm Mon-Fri | 2 hours | Intraday updates |
| Weekend | 3pm Sunday | 42 hours | Weekend recap |
| Sunday night | 9pm Sunday | 6 hours | Pre-market prep |

### Timezone Options

Change the `tz` field to match your timezone:

- `America/Chicago` (CT) — default
- `America/New_York` (ET)
- `America/Los_Angeles` (PT)
- `Europe/London` (GMT/BST)
- `Asia/Tokyo` (JST)

### Score Threshold

Adjust `-s N` in the twag command to change signal sensitivity:

- `-s 6` — Default, good signal/noise balance
- `-s 7` — Higher threshold, fewer tweets
- `-s 8` — Only high-signal (stricter)

## Daily Maintenance

Consider running these maintenance tasks daily (e.g., at 3am):

```bash
# Apply account decay (reduces boost over time)
twag accounts decay

# Prune old tweets (keeps database size manageable)
twag prune --days 14
```

Add to your systemd service or launchd plist if desired.

## Monitoring

### Check recent runs

```bash
# systemd
journalctl --user -u twag-aggregator.service --since "1 hour ago"

# launchd
tail -100 /tmp/twag-aggregator.log
```

### Check data freshness

```bash
twag stats --today
```

### Test the pipeline manually

```bash
twag fetch --no-tier1 && twag process --limit 10
twag search "market" --today
```

## Troubleshooting

### Timer not running

```bash
# systemd
systemctl --user status twag-aggregator.timer
systemctl --user restart twag-aggregator.timer

# launchd
launchctl list | grep twag
launchctl unload ~/Library/LaunchAgents/com.twag.aggregator.plist
launchctl load ~/Library/LaunchAgents/com.twag.aggregator.plist
```

### Environment variables not loading

Ensure your service sources `~/.env` or uses `EnvironmentFile`:

```ini
# systemd
EnvironmentFile=%h/.env
```

### PATH issues

Add explicit paths to the service:

```bash
# In ExecStart
/bin/bash -c 'export PATH="$HOME/.local/bin:$PATH" && source ~/.env && twag fetch'
```
