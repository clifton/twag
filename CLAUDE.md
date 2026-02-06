# CLAUDE.md

Repository guidance for agents working in this project.

## Scope

This repository provides:

- CLI pipeline (`twag`)
- SQLite storage + FTS search
- FastAPI backend (`twag/web/`)
- React frontend (`twag/web/frontend/`)
- OpenClaw skill definition (`SKILL.md`)

`AGENTS.md` in this repo points here; treat this file as the primary instruction source.

## OpenClaw Skill Context

This project is also an OpenClaw skill. `SKILL.md` metadata controls discovery/installation and runtime requirements.

### Skill loading precedence

1. Workspace skills (`./skills/`)
2. Managed skills (`~/.claude/skills/`)
3. Bundled skills

### `{baseDir}` placeholder

When OpenClaw loads a skill, `{baseDir}` is replaced with the installed skill directory.

## Current Architecture

Pipeline:

`FETCH -> PROCESS -> DIGEST`

Core modules:

- `twag/cli.py`: command entry points
- `twag/fetcher.py`: `bird` integration + tweet parsing
- `twag/processor.py`: orchestration (triage, enrichment, media/article passes)
- `twag/scorer.py`: LLM scoring and article summarization
- `twag/db.py`: schema, migrations, query layer
- `twag/renderer.py`: markdown digest generation
- `twag/link_utils.py`: link normalization and embed classification
- `twag/article_visuals.py`: data-visual selection for article summaries
- `twag/web/`: FastAPI app + routes
- `twag/web/frontend/`: React feed UI

## Key Runtime Behaviors

### Link normalization (digest + web)

Implemented in `twag/link_utils.py`.

URL short-link expansion (`t.co` -> final URL) runs during `twag process` and is
persisted to `tweets.links_json` with `links_expanded_at`. Digest rendering and
web API routes are read-only consumers of stored expanded links.

Rules:

- Remove self links (tweet links pointing to the current tweet)
- Convert twitter/x links to other tweets into inline quote link metadata
- Expand non-twitter short URLs (best effort) during processing and render as external links
- Prune trailing unresolved `t.co` links that are likely self/media pointers:
  - for media tweets, and
  - for mixed-link tweets where another link in the same post resolved externally

### X Article processing

For article tweets (`is_x_article`), processor stores:

- `article_summary_short`
- `article_primary_points_json`
- `article_action_items_json`
- `article_top_visual_json`
- `article_processed_at`

`article_visuals.py` prioritizes relevant visuals (`chart`, `table`, `document`, `screenshot`) and suppresses obvious noise.

### Web feed rendering

`twag/web/routes/tweets.py` provides display-ready fields:

- `display_content`
- `quote_embed`
- `inline_quote_embeds`
- `external_links`

Frontend `TweetCard` emphasizes article summaries, primary/action points, and visuals; inline URL rendering comes from `TweetContent`.

## CLI Surface (Current)

Defined in `twag/cli.py`:

- `init`, `doctor`
- `fetch`
- `process`
- `analyze`
- `digest`
- `accounts` (`list`, `add`, `promote`, `mute`, `demote`, `decay`, `boost`, `import`)
- `narratives list`
- `stats`, `prune`, `export`
- `config` (`show`, `path`, `set`)
- `db` (`path`, `shell`, `init`, `rebuild-fts`, `dump`, `restore`)
- `search`
- `web`

If command behavior changes, update `README.md` and this file in the same PR.

## Dev Environment

### Python

```bash
pip install -e .
pip install -e ".[dev]"
```

### Frontend

```bash
cd twag/web/frontend
npm install
npm run dev
npm run build
```

Dev server behavior:

- `twag web --dev` starts Vite on `http://localhost:8080`
- Vite proxies `/api` to `http://localhost:5173` by default
- `twag web` (non-dev) serves FastAPI; if `twag/web/frontend/dist/` exists, it serves the SPA

## Validation Expectations

When changing Python code:

```bash
uv run ruff format <files>
uv run ruff check <files>
uv run pytest -q <relevant tests>
```

When changing frontend code:

```bash
cd twag/web/frontend
npm run build
```

Favor targeted tests plus adjacent integration tests for changed behavior.

## Documentation Expectations

Keep docs aligned with current code:

- `README.md`: user-facing commands and behavior
- `CLAUDE.md`: agent/developer operating guidance
- `AGENTS.md`: short pointer to `CLAUDE.md`

Avoid absolute machine-specific paths in repository docs.

## Repository Agent Rules

### Temporary artifacts

- Place screenshots/debug exports/one-off files in `tmp/`
- Do not leave temporary artifacts at repository root
- `tmp/` should be gitignored except `tmp/.gitkeep`

### Commit hygiene

- Keep commits focused and atomic
- Run formatting/lint/tests before committing
- Do not commit temporary artifacts unless explicitly requested
