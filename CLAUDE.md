# CLAUDE.md

Repository guidance for AI agents and developers working in this project.

## Overview

**twag** is a Twitter/X market signal aggregator that:
- Fetches tweets via the `bird` CLI
- Scores them for market relevance using LLMs
- Generates digests and serves a web feed

This project doubles as an OpenClaw skill for agent automation.

## Architecture

```
FETCH → PROCESS → DIGEST
```

**Core packages:**
- `twag/models/` — Pydantic data models (tweet, scoring, media, links, config, API)
- `twag/auth.py` — Shared credential and env-file parsing
- `twag/config.py` — Runtime config (paths, defaults, following file)
- `twag/db/` — SQLite database layer (schema, connections, CRUD, search, maintenance, accounts, narratives, reactions, time utils)
- `twag/fetcher/` — bird CLI integration + tweet parsing/extraction
- `twag/scorer/` — LLM scoring, prompts, and client management
- `twag/processor/` — Pipeline orchestration (storage, dependencies, triage, pipeline)
- `twag/cli/` — Rich-enhanced Click CLI commands
- `twag/notifier.py` — Telegram alert delivery
- `twag/renderer.py` — Markdown digest generation
- `twag/tables.py` — Rich table formatting for CLI output
- `twag/media.py` — Media handling utilities
- `twag/link_utils.py` — URL expansion and embed classification
- `twag/article_visuals.py` — Visual selection for X Articles
- `twag/article_sections.py` — Article section extraction
- `twag/web/` — FastAPI backend (app, tweet_utils, routes: tweets, context, prompts, reactions)
- `twag/web/frontend/` — React feed UI

## Key Files

| File | Purpose |
|------|---------|
| `README.md` | User documentation |
| `INSTALL.md` | Step-by-step installation guide |
| `SKILL.md` | OpenClaw skill metadata + quick reference |
| `CLAUDE.md` | This file — agent/developer guidance |
| `TELEGRAM_DIGEST_FORMAT.md` | Telegram output formatting rules |
| `SUGGESTED_CRON_SCHEDULE.md` | Automation setup guide |

## OpenClaw Skill Context

The `SKILL.md` frontmatter controls skill discovery and installation:

```yaml
metadata:
  openclaw:
    requires:
      bins: ["twag", "bird"]
      env: ["GEMINI_API_KEY", "AUTH_TOKEN", "CT0"]
```

`{baseDir}` in SKILL.md is replaced with the skill directory at runtime.

## Development

### Setup

```bash
pip install -e ".[dev]"
```

### Lint & Format

```bash
uv run ruff format .
uv run ruff check .
```

### Test

```bash
uv run pytest
```

### Frontend

```bash
cd twag/web/frontend
npm install
npm run build    # Production build
npm run dev      # Dev server (port 8080)
```

## Validation Before Commit

1. Format: `uv run ruff format <files>`
2. Lint: `uv run ruff check <files>`
3. Test: `uv run pytest -q <relevant tests>`
4. If frontend changed: `cd twag/web/frontend && npm run build`

## Documentation Expectations

Keep in sync:
- `README.md` — User-facing commands and behavior
- `SKILL.md` — OpenClaw-specific quick reference
- `CLAUDE.md` — Developer/agent operating guidance
- `INSTALL.md` — Step-by-step installation

Avoid absolute machine-specific paths in docs.

## Temporary Artifacts

- Use `tmp/` for screenshots, debug exports, one-off files
- Don't leave artifacts at repository root
- `tmp/` is gitignored except `.gitkeep`

## Runtime Behaviors

### Link normalization

URL expansion (`t.co` → final URL) runs during `twag process` and persists to `tweets.links_json`. Digest rendering and web API are read-only consumers.

Rules:
- Remove self-links (tweet links to current tweet)
- Convert twitter/x links to quote embeds
- Expand non-twitter short URLs
- Prune trailing unresolved t.co links for media tweets

### X Article processing

For article tweets (`is_x_article`), the processor stores:
- `article_summary_short`
- `article_primary_points_json`
- `article_action_items_json`
- `article_top_visual_json`

Visual selection prioritizes data-oriented images (charts, tables, documents).

### Web feed rendering

`twag/web/routes/tweets.py` provides display-ready fields:
- `display_content`
- `quote_embed`
- `inline_quote_embeds`
- `external_links`

## CLI Surface

Defined in `twag/cli/`:

- **Setup:** `init`, `doctor`
- **Pipeline:** `fetch`, `process`, `analyze`, `digest`
- **Accounts:** `list`, `add`, `promote`, `demote`, `mute`, `boost`, `decay`, `import`
- **Query:** `search`, `narratives list`
- **Maintenance:** `stats`, `prune`, `export`
- **Config:** `show`, `path`, `set`
- **Database:** `path`, `shell`, `init`, `rebuild-fts`, `dump`, `restore`
- **Web:** `web`

If command behavior changes, update `README.md` and `SKILL.md` in the same PR.

## Commit Hygiene

- Keep commits focused and atomic
- Run formatting/lint/tests before committing
- Don't commit temporary artifacts unless explicitly requested
- Write descriptive commit messages
