# Suggested Cron Schedule for twag

## Overview

twag works best with two layers of automation:

1. **Data Collection** - Frequent fetch/process cycle (every 15 min)
2. **Digest Delivery** - Telegram summaries at key market times

## Data Collection

### Linux (systemd)

Create two unit files:

**~/.config/systemd/user/twag-aggregator.service**
```ini
[Unit]
Description=TWAG Twitter Aggregator
After=network.target

[Service]
Type=oneshot
ExecStart={baseDir}/scripts/cron-runner.sh full
WorkingDirectory=%h
Environment=PATH=%h/.local/bin:%h/.cargo/bin:/usr/local/bin:/usr/bin:/bin
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

Enable with:
```bash
systemctl --user daemon-reload
systemctl --user enable --now twag-aggregator.timer

# Check status
systemctl --user status twag-aggregator.timer
systemctl --user list-timers
```

### macOS (launchd)

Create **~/Library/LaunchAgents/com.twag.aggregator.plist**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.twag.aggregator</string>
    <key>ProgramArguments</key>
    <array>
        <string>{baseDir}/scripts/cron-runner.sh</string>
        <string>full</string>
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
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

Load with:
```bash
launchctl load ~/Library/LaunchAgents/com.twag.aggregator.plist

# Check status
launchctl list | grep twag
```

## Telegram Digests (OpenClaw cron)

Add these jobs to `~/.openclaw/cron/jobs.json`. Replace `YOUR_CHAT_ID` with your Telegram chat ID.

```json
{
  "version": 1,
  "jobs": [
    {
      "agentId": "main",
      "name": "twag morning digest",
      "schedule": {
        "kind": "cron",
        "expr": "0 7 * * 1-5",
        "tz": "America/Chicago"
      },
      "sessionTarget": "isolated",
      "wakeMode": "next-heartbeat",
      "payload": {
        "kind": "agentTurn",
        "message": "Generate an overnight tweet digest. Run: twag search --time 10h -s 6 -f full. Group tweets by theme, condense into bullets, and format per skills/twag/TELEGRAM_DIGEST_FORMAT.md. Use [🔗](url) for citations, [📊](url) for charts. If no notable tweets found, reply NO_REPLY.",
        "thinking": "medium",
        "deliver": true,
        "channel": "telegram",
        "to": "YOUR_CHAT_ID"
      },
      "enabled": true
    },
    {
      "agentId": "main",
      "name": "twag 2-hour digest",
      "schedule": {
        "kind": "cron",
        "expr": "0 9,11,13,15,17,19,21 * * 1-5",
        "tz": "America/Chicago"
      },
      "sessionTarget": "isolated",
      "wakeMode": "next-heartbeat",
      "payload": {
        "kind": "agentTurn",
        "message": "Generate a 2-hour tweet digest. Run: twag search --time 2h -s 6 -f full. Group by theme, condense into bullets, format per skills/twag/TELEGRAM_DIGEST_FORMAT.md. Use [🔗](url) for citations, [📊](url) for charts. If no notable tweets found, reply NO_REPLY.",
        "thinking": "medium",
        "deliver": true,
        "channel": "telegram",
        "to": "YOUR_CHAT_ID"
      },
      "enabled": true
    },
    {
      "agentId": "main",
      "name": "twag weekend digest",
      "schedule": {
        "kind": "cron",
        "expr": "0 15 * * 0",
        "tz": "America/Chicago"
      },
      "sessionTarget": "isolated",
      "wakeMode": "next-heartbeat",
      "payload": {
        "kind": "agentTurn",
        "message": "Generate a weekend tweet digest covering Friday night through Sunday afternoon. Run: twag search --time 42h -s 6 -f full. Group tweets by theme, condense into bullets, format per skills/twag/TELEGRAM_DIGEST_FORMAT.md. Use [🔗](url) for citations, [📊](url) for charts. If no notable tweets found, reply NO_REPLY.",
        "thinking": "medium",
        "deliver": true,
        "channel": "telegram",
        "to": "YOUR_CHAT_ID"
      },
      "enabled": true
    },
    {
      "agentId": "main",
      "name": "twag sunday night digest",
      "schedule": {
        "kind": "cron",
        "expr": "0 21 * * 0",
        "tz": "America/Chicago"
      },
      "sessionTarget": "isolated",
      "wakeMode": "next-heartbeat",
      "payload": {
        "kind": "agentTurn",
        "message": "Generate a Sunday evening tweet digest. Run: twag search --time 6h -s 6 -f full. Group by theme, condense into bullets, format per skills/twag/TELEGRAM_DIGEST_FORMAT.md. Use [🔗](url) for citations, [📊](url) for charts. If no notable tweets found, reply NO_REPLY.",
        "thinking": "medium",
        "deliver": true,
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
| Morning | 7am CT Mon-Fri | 10 hours | Overnight summary |
| 2-hour | 9am-9pm CT Mon-Fri | 2 hours | Intraday updates |
| Weekend | 3pm CT Sunday | 42 hours | Weekend recap |
| Sunday night | 9pm CT Sunday | 6 hours | Pre-market prep |

## Customization

### Timezone
Change `tz` field in each job. Common options:
- `America/Chicago` (CT) - default
- `America/New_York` (ET)
- `America/Los_Angeles` (PT)
- `Europe/London` (GMT/BST)

### Score Threshold
Adjust `-s N` in the `twag search` command to change signal sensitivity:
- `-s 6` - Default, good balance of signal/noise
- `-s 7` - Higher threshold, fewer tweets
- `-s 8` - Only high-signal tweets (stricter)

### Telegram Setup
1. Create a bot via [@BotFather](https://t.me/botfather)
2. Set `TELEGRAM_BOT_TOKEN` environment variable
3. Get your chat ID by messaging the bot and checking `/getUpdates`
4. Replace `YOUR_CHAT_ID` in the jobs above

## Related Documentation

- [TELEGRAM_DIGEST_FORMAT.md]({baseDir}/TELEGRAM_DIGEST_FORMAT.md) - How to format digests for Telegram
- [SKILL.md]({baseDir}/SKILL.md) - Full twag command reference
