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
```

## Commands

### Search (most common)

```bash
# Browse mode (no query) — uses rich FeedTweet data
twag search --today -s 7             # High-signal tweets since market close
twag search --time 2h -s 6 -f json -n 50  # Rich JSON for digests
twag search -c fed_policy --time 7d  # Browse by category

# Full-text search mode
twag search "query"                  # FTS5 search
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
```

## Scoring Tiers

| Score | Level | Behavior |
|-------|-------|----------|
| 8-10 | Alert | Telegram alert |
| 7 | High signal | Enriched, in digests |
| 5-6 | Market relevant | In digests |
| 3-4 | News/context | Searchable |
| 0-2 | Noise | Filtered out |

## Categories

`fed_policy`, `inflation`, `job_market`, `macro_data`, `earnings`, `equities`, `rates_fx`, `credit`, `banks`, `consumer_spending`, `capex`, `commodities`, `energy`, `metals_mining`, `geopolitical`, `sanctions`, `tech_business`, `ai_advancement`, `crypto`, `noise`

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `AUTH_TOKEN` | Yes | Twitter auth cookie |
| `CT0` | Yes | Twitter ct0 cookie |
| `GEMINI_API_KEY` | Yes | LLM triage |
| `ANTHROPIC_API_KEY` | No | Enrichment |
| `TELEGRAM_BOT_TOKEN` | No | Alerts |
| `TELEGRAM_CHAT_ID` | No | Alert destination |

## Producing digests — editorial rules

When producing a digest for Telegram, chat, or any market-note output, follow the format doc at [{baseDir}/TELEGRAM_DIGEST_FORMAT.md]({baseDir}/TELEGRAM_DIGEST_FORMAT.md) plus the editorial rules below.

Source command (adjust window and limit to taste — prefer a broad pull and condense after retrieval):

```bash
twag search --time 2h -s 6 -f json -n 100
```

Treat the JSON output as source material, not as the final answer. Rewrite it into the final digest. Do not try to solve deduplication, attribution, or brevity mechanically. Use editorial judgment.

**Audience: someone consuming market information at a glance. Every unnecessary word wastes their time.**

### Rule 1: No added color. Ever.

Bullets are strictly factual. Never tack on a trailing clause that interprets, frames, themes, or synthesizes what the facts mean. No "AI-style" commentary — no phrases like "escalation still driving barrel-control regime", "signaling continued uncertainty", "reinforcing the risk-off tone", "underscoring fragility", "highlighting the shift". State the facts. Stop. The reader interprets.

Bad:

```text
• Trump ordered Navy to engage mine-laying boats, tripled minesweeper activity, then said Hormuz is effectively sealed until Iran deal, escalation still driving barrel-control regime
```

The trailing clause `escalation still driving barrel-control regime` is unnecessary. It adds zero information and makes the bullet look generated.

Better:

```text
• Trump ordered Navy to engage Iran mine-laying boats; minesweeper activity tripled; Hormuz "effectively sealed until Iran deal"
```

Before emitting any bullet, scan for trailing interpretive clauses and cut them.

### Rule 2: Compression

- compress aggressively; no arbitrary fixed top-N cap unless the user explicitly asks
- every bullet must be as concise as possible and should survive a second compression pass
- default to one-line bullets; use a second line only when the point would otherwise break
- fragments beat sentences; do not try to make bullets read like polished prose
- if a bullet still reads like a normal sentence, compress again
- one bullet should usually represent one distinct development or takeaway, not one tweet
- before returning, ask: "can I delete 20 percent more words from each bullet?" If yes, do it

### Rule 3: Grouping and merging

- merge duplicate or near-duplicate items into a single bullet; gather their citations at the end
- never emit labels like `Duplicate:`; fold those links into the merged bullet
- when multiple tweets support the same claim, keep the strongest phrasing once and attach multiple citations like `[🔗](url1) [📊](url2)`
- preserve materially distinct updates even inside the same theme; do not merge unrelated developments just because they share a category

### Rule 4: Attribution

- omit source/author attribution by default
- include attribution only when the identity materially changes the meaning of the item
- attribution matters: a CEO speaking about their company, a Fed or White House official, a named analyst making a non-consensus call, a politician announcing policy, a well-known domain expert whose identity is itself the news
- attribution usually does not matter: aggregator/newswire handles like `financialjuice`, `DeItaone`, `sentdefender`, `zerohedge`, `Barchart`, and similar repost/alert accounts
- if attribution matters, keep it brief and natural inside the bullet; do not mechanically prefix every line with a handle
- prefer fact-first wording; strip filler like `reports indicate`, `speculation on`, `analysis of`, `reportedly`

### Rule 5: Section discipline

- default to roughly 4-6 sections and usually 2-4 bullets per section; only exceed that when the signal clearly earns it
- if three bullets say the same thing, they must become one bullet
- drop weak opinion-only tweets unless the person or phrasing itself is the news
- do not include generic reactions, vague warnings, or "watch this" commentary unless they add a concrete fact
- do not repeat the same fact in multiple sections
- if a section cannot produce at least 2 high-signal bullets, fold it into another section or cut it entirely

### Examples

Bad:

```text
• financialjuice: Reports indicate no damage to Iran oil infrastructure following US-Israeli attack. [🔗](a)
• DeItaone: Iranian sources report no disruptions to oil facilities at Kharg Island despite geopolitical tensions. [🔗](b)
• Duplicate: U.S. State Dept advisory for Bahrain amid Iran escalation risk. [📊](c)
```

Better:

```text
• No reported damage to Iran oil infrastructure after the strike. [🔗](a) [🔗](b)
• U.S. State Department issued a Bahrain advisory amid escalation risk. [📊](c)
```

Bad:

```text
• sundarpichai: Google CEO Sundar Pichai discusses AGI roadmap and future of Google Search. [🔗](d)
```

Better:

```text
• Sundar Pichai: Google is framing its AGI roadmap around the future of Search. [🔗](d)
```

### Before-return checklist

- headers are **BOLD CAPS**
- bullets use `•`
- every bullet ends with `[🔗](url)` or `[📊](url)`
- no `Source:` / `📰` / `💡` summary-card formatting survived
- every bullet is the shortest version that still carries the point
- **no bullet has a trailing interpretive clause** (e.g. "…driving X regime", "…signaling Y", "…reinforcing Z")
- no attribution prefix on aggregator/newswire accounts

For OpenClaw users: set `delivery.mode: "direct"` in cron jobs to preserve `[🔗](url)` and `[📊](url)` links across the announce path.

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
