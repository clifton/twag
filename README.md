# twag

Twitter/X market-signal aggregation with LLM triage, enrichment, article summarization, and a web feed.

## What It Does

- Fetches timeline/user/search/status data via `bird`
- Stores tweets in SQLite with dedupe and FTS search
- Scores and categorizes tweets with LLMs
- Enriches high-signal tweets with deeper analysis
- Summarizes X Articles into:
  - short summary
  - primary points + reasoning
  - actionable items + triggers
  - data-oriented visuals (top visual first)
- Renders daily markdown digests
- Serves a FastAPI + React web UI

## Requirements

- Python `>=3.10`
- `bird` CLI in `PATH`
- Env vars:
  - `GEMINI_API_KEY` (triage + vision)
  - `AUTH_TOKEN` and `CT0` (Twitter auth for `bird`)
- Optional:
  - `ANTHROPIC_API_KEY` (deep enrichment)
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (alerts)

## Install

```bash
# from source
pip install -e .

# with dev tools
pip install -e ".[dev]"
```

## Quick Start

```bash
# 1) bootstrap config + db
twag init

# 2) verify dependencies/env
twag doctor

# 3) pull data
twag fetch

# 4) score + enrich
twag process

# 5) generate digest
twag digest

# 6) open web feed
twag web
```

## Data Paths

twag follows XDG defaults:

- Config: `~/.config/twag/config.json`
- Data dir: `~/.local/share/twag/`
- DB: `~/.local/share/twag/twag.db`
- Digests: `~/.local/share/twag/digests/`
- Following list: `~/.local/share/twag/following.txt`

Override with:

- Env var: `TWAG_DATA_DIR`
- Config key: `paths.data_dir`

## Pipeline

1. `fetch` phase
- Pull tweets from home/user/search/bookmarks or a single status
- Store normalized tweet rows

2. `process` phase
- Batch triage scoring
- Optional enrichment for higher-signal tweets
- Optional quote reprocessing for today’s quoted tweets
- Optional X Article summarization (score-gated)

3. `digest` phase
- Query processed tweets by date and score
- Render grouped markdown output

## Link Handling Rules

Normalized link behavior is shared across digest + web feed:

- Self-links to the same tweet are removed
- Twitter/X links to other tweets become inline quote embeds when available
- Non-twitter links are expanded and rendered as clickable URLs
- Trailing unresolved `t.co` links that look like self/media pointers are pruned
  - for media tweets
  - and for mixed-link tweets where another URL already resolves externally

## X Article Output

For article tweets (`is_x_article`), twag stores and renders:

- `article_summary_short`
- `article_primary_points` (point + reasoning + evidence)
- `article_action_items` (action + trigger + horizon + confidence + tickers)
- `article_top_visual`
- additional relevant visuals selected from media

Visual selection is data-oriented (chart/table/document/screenshot), with noisy/irrelevant images filtered out when possible.

## CLI Reference

### Setup

```bash
twag init
twag init --force
twag doctor
```

### Fetch

```bash
# default home fetch (+ tier1 + bookmarks)
twag fetch

# single status (id or url)
twag fetch 2019488673935552978
twag fetch https://x.com/undrvalue/status/2019488673935552978

# user/search sources
twag fetch --source user --handle @NickTimiraos --count 50
twag fetch --source search --query "Fed Powell rate" --count 30

# source controls
twag fetch --no-tier1 --no-bookmarks
twag fetch --delay 2 --stagger 10
```

### Process

```bash
# process queued tweets
twag process

# process one already-fetched status
twag process 2019488673935552978
twag process https://x.com/undrvalue/status/2019488673935552978

# options
twag process --limit 100
twag process --dry-run
twag process --model gemini-3-flash-preview
twag process --no-notify
twag process --no-reprocess-quotes
```

### Analyze (one-shot)

```bash
# fetch + process + print analysis
twag analyze 2019488673935552978
twag analyze https://x.com/undrvalue/status/2019488673935552978

# force refresh
twag analyze 2019488673935552978 --reprocess
```

### Digest

```bash
twag digest
twag digest --date 2026-02-06
twag digest --stdout
twag digest --min-score 6
```

### Accounts

```bash
twag accounts list
twag accounts list --tier 1 --muted

twag accounts add @handle --tier 2 --category tech_business
twag accounts promote @handle
twag accounts demote @handle --tier 2
twag accounts mute @handle
twag accounts boost @handle --amount 10
twag accounts decay --rate 0.05
twag accounts import --tier 2
```

### Narratives

```bash
twag narratives list
```

### Search

```bash
twag search "inflation fed"
twag search "rate hike" --category fed_policy --min-score 7
twag search "NVDA" --author zerohedge --time 7d
twag search "earnings" --ticker AAPL --today

# output + sorting
twag search "fed" --format brief
twag search "fed" --format full
twag search "fed" --format json
twag search "fed" --order rank
```

### Stats / Maintenance

```bash
twag stats
twag stats --today
twag stats --date 2026-02-06

twag prune --days 14
twag prune --days 14 --dry-run

twag export --days 7 --format json
```

### Config

```bash
twag config show
twag config path
twag config set llm.triage_model gemini-3-flash-preview
twag config set scoring.alert_threshold 9
twag config set paths.data_dir ./data
```

### DB

```bash
twag db path
twag db shell
twag db init
twag db rebuild-fts

twag db dump
twag db dump backup.sql
twag db dump --stdout

twag db restore backup.sql --force
twag db restore backup.sql.gz --force
```

### Web

```bash
# production-style server
twag web

# custom host/port
twag web --host 0.0.0.0 --port 5173

# dev mode (Vite + API)
twag web --dev
```

Notes:
- In dev mode, Vite runs on `http://localhost:8080`.
- API target defaults to `http://localhost:5173` unless you change `--port`.

## Security

**`twag web` is designed for local/trusted-network use only.** The API endpoints are unauthenticated. Do not expose the server to the public internet without adding your own authentication layer.

The default bind address is `0.0.0.0` (all interfaces). To restrict to local-only access, use:

```bash
twag web --host 127.0.0.1
```

## Scoring Tiers

- `high_signal`: strongest actionable content
- `market_relevant`: useful market context/opinion
- `news`: informational context
- `noise`: low signal

## Development

```bash
# python lint/format/test
uv run ruff format .
uv run ruff check .
uv run pytest

# frontend
cd twag/web/frontend
npm install
npm run dev
npm run build
```

## Temporary Artifacts

Use repo-local `tmp/` for screenshots/debug artifacts. Root-level ad-hoc artifacts should be avoided.

## License

MIT. See `LICENSE`.
