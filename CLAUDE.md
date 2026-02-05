# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## OpenClaw Skill Context

This project is an **OpenClaw skill**, not just a standalone CLI. The skill is defined in `SKILL.md` and loaded by OpenClaw agents.

### How OpenClaw Loads Skills

OpenClaw searches for skills in this precedence order:
1. **Workspace skills** - `./skills/` in the current project
2. **Managed skills** - `~/.claude/skills/` (installed via ClawdHub)
3. **Bundled skills** - Built into the agent

When a skill matches its `read_when` conditions, OpenClaw loads the SKILL.md instructions into context.

### The `{baseDir}` Placeholder

In SKILL.md instructions, `{baseDir}` is replaced with the skill's installation directory at load time. This allows skills to reference their own files without hardcoding paths.

## SKILL.md Structure

The skill definition lives in `SKILL.md` with YAML frontmatter:

### Required Fields
- `name` - Skill identifier (e.g., `twag`)
- `description` - Brief description for skill discovery

### Key Optional Fields Used Here

```yaml
read_when:        # Conditions that trigger skill loading
  - Processing Twitter/X feed for market signals
  - Searching for market-relevant tweets

homepage: https://github.com/clifton/twag

metadata:         # ClawdBot/OpenClaw gating
  clawdbot:
    emoji: "📊"
    requires:
      bins: [twag, bird]    # Required binaries
      env: [GEMINI_API_KEY, AUTH_TOKEN, CT0]  # Required env vars
    install:
      - id: pip
        kind: pip
        package: twag
        bins: [twag]

allowed-tools: Bash(twag:*)  # Tool permissions pattern
```

### Modifying Requirements

To add new binary/env requirements, update the `metadata.clawdbot.requires` section. The `allowed-tools` field controls which Bash commands the agent can run without prompting.

## Build & Development

```bash
pip install -e .           # Install for development
pip install -e ".[dev]"    # With dev dependencies
pytest                     # Run all tests
pytest -v tests/test_fetcher.py::test_parse_tweet  # Single test
```

### Frontend (React SPA)

```bash
cd twag/web/frontend
npm install                # Install dependencies
npm run dev                # Dev server on :5173 (proxies /api to :8080)
npm run build              # Production build to dist/
```

When `twag/web/frontend/dist/` exists, `twag web` serves the SPA. Otherwise it has no frontend.
The frontend is a React 19 + TypeScript SPA using Vite, Tailwind CSS 4, shadcn/ui (dark theme),
TanStack Query v5, and React Router v7. CodeMirror 6 is used for the prompt editor.

## Architecture Overview

twag is a three-phase pipeline for aggregating market-relevant Twitter content:

```
FETCH → PROCESS → DIGEST
```

### Core Modules

| Module | Purpose |
|--------|---------|
| `cli.py` | Click CLI entry points |
| `fetcher.py` | Bird CLI wrapper for fetching tweets |
| `processor.py` | Pipeline orchestration (store, triage, enrich) |
| `scorer.py` | LLM scoring engines (Gemini for triage, Claude for enrichment) |
| `db.py` | SQLite database layer with FTS5 search |
| `renderer.py` | Markdown digest generation |
| `notifier.py` | Telegram alerts |
| `config.py` | XDG-compliant configuration |

### Data Flow

1. **Fetch**: `fetcher.py` calls `bird` CLI → `processor.store_fetched_tweets()` dedupes and stores
2. **Process**: `processor.process_unprocessed()` → `scorer.triage_tweets_batch()` scores in batches → high-signal tweets get `scorer.enrich_tweet()`
3. **Digest**: `renderer.render_digest()` queries by date/score → groups by signal tier → outputs markdown

### LLM Configuration

- **Triage**: Fast batch scoring (default: `gemini-3-flash-preview`)
- **Enrichment**: Deep analysis for high-signal tweets (default: `claude-opus-4-5-20251101`)
- **Vision**: Media analysis (default: `gemini-3-flash-preview`)

### Database Schema

Main tables in SQLite (`twag.db`):
- `tweets` - Content, scores, categories, media
- `accounts` - Tracked accounts with tier/weight/stats
- `narratives` - Emerging themes
- `fts_tweets` - FTS5 full-text search index

### Web Architecture

The web interface is a React SPA served by FastAPI:
- **Backend** (`twag/web/`): FastAPI app with JSON API routes (`/api/*`)
- **Frontend** (`twag/web/frontend/`): React SPA (Vite + TypeScript + Tailwind)
- **Shared utils** (`twag/web/tweet_utils.py`): Tweet link extraction/cleaning helpers
- **API routes**: `routes/tweets.py`, `routes/reactions.py`, `routes/prompts.py`, `routes/context.py`
- **SPA serving**: `app.py` serves `frontend/dist/index.html` for all non-API routes

### Key Patterns

**Database context manager:**
```python
with get_connection() as conn:
    # queries here
    conn.commit()  # explicit commit required
```

**Progress callbacks:** Functions accept `progress_cb`, `status_cb`, `total_cb` for CLI progress bars.

**Market-aware time:** "today" means since previous 4pm ET market close, not midnight.
