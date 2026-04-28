# Architecture

twag is a Twitter/X market-signal aggregator built around three sequential
phases:

```
FETCH ──► PROCESS ──► DIGEST
```

Each phase is exposed as a CLI command (`twag fetch`, `twag process`,
`twag digest`), can be run independently, and persists state to a single
SQLite database.

## Phase overview

### 1. FETCH

Pulls tweets from Twitter/X via the [`bird`](https://github.com/steipete/bird)
CLI and inserts them into the local database. Sources:

- Home timeline
- Per-user timelines (`--source user --handle`)
- Search queries (`--source search --query`)
- Tier-1 account list (rotated, paced)
- Bookmarks

Module: `twag/fetcher/`

- `bird_cli.py` — Subprocess wrapper around `bird` with retry, rate-limit
  awareness, and per-call latency metrics.
- `extractors.py` — Parses bird JSON into the internal `Tweet` model and
  related entities (media, links, quoted/replied IDs).

The fetch-and-store layer (`twag/processor/storage.py`) calls the fetcher,
inserts new tweets via `insert_tweet`, upserts authors into the `accounts`
table, marks bookmarks, and logs each call to `fetch_log`. When
`quote_depth > 0` it also walks and stores quote/reply/inline-link chains.

### 2. PROCESS

Scores unprocessed tweets via LLM, derives a signal tier, and enriches
high-signal tweets with vision/article/text analysis.

Module: `twag/processor/` (orchestration), `twag/scorer/` (LLM calls).

The pipeline in `processor/pipeline.py::process_unprocessed` runs these
stages in order:

1. **Load config** (batch size, score thresholds, concurrency, quote depth).
2. **Fetch unprocessed rows** (or use caller-supplied rows).
3. **Dependency expansion** — BFS-walk quote/reply/inline-link chains, fetch
   missing tweets, and add unprocessed dependencies to the batch
   (`dependencies._expand_unprocessed_with_dependencies`).
4. **Link expansion** — concurrently expand `t.co` URLs in `links_json`,
   persist to the DB.
5. **Tier-1 lookup** — load tier-1 handles so their tweets skip the
   long-content summarizer.
6. **Batch triage** — call the triage LLM in batches; for X Articles the
   triage text is the article body rather than the tweet text.
7. **Per-result post-processing** — for each result:
   - Derive `signal_tier` from the score using config-driven thresholds.
   - Persist score, categories, summary, tier, tickers.
   - Update author account stats.
   - If score ≥ `min_score_for_media` and the tweet has media: vision
     analysis (parallel pool).
   - If score ≥ `min_score_for_analysis`: enrichment (insight,
     implications, narratives, ticker refinement).
   - If the tweet is an X Article and score ≥
     `min_score_for_article_processing`: article summary, primary points,
     action items, top visual.
   - If content > 500 chars, score ≥ 5, author is not tier-1: produce a
     `content_summary`.
8. **Future resolution** — drain text/vision/triage thread pools, write
   results back on the owner thread.
9. **Commit** and emit `pipeline.process_unprocessed.*` metrics.

The scorer layer (`twag/scorer/`) wraps the Anthropic and Gemini SDKs:

- `llm_client.py` — Provider clients with retry, token accounting, and
  latency/error metrics.
- `prompts.py` — Triage and enrichment prompt definitions (also editable
  via the `prompts` table at runtime).
- `scoring.py` — Triage, enrichment, article summarization, content
  summarization, vision analysis.

### 3. DIGEST

Generates a markdown digest of the day's high-signal tweets, optionally
delivered via Telegram.

- `twag/renderer.py` — Markdown digest rendering grouped by theme.
- `twag/notifier.py` — Telegram delivery (used by `twag process --notify`
  for real-time alerts on score ≥ 8 tweets).
- `twag/cli/digest.py` — `twag digest` command.

Telegram formatting rules live in
[`TELEGRAM_DIGEST_FORMAT.md`](../TELEGRAM_DIGEST_FORMAT.md).

## Module map

| Module | Responsibility |
|--------|---------------|
| `twag/auth.py` | Shared credential/env-file parsing |
| `twag/config.py` | Runtime config (paths, defaults, following file) |
| `twag/models/` | Pydantic models (tweet, scoring, media, links, config, API, db_models) |
| `twag/db/` | SQLite layer: schema, connection, tweets, search, accounts, narratives, reactions, prompts, context_commands, alerts, maintenance, time utilities |
| `twag/fetcher/` | bird CLI integration + tweet parsing |
| `twag/scorer/` | LLM scoring, prompts, client management |
| `twag/processor/` | Pipeline orchestration (storage, dependencies, triage, pipeline) |
| `twag/cli/` | Click commands (Rich-enhanced output) |
| `twag/notifier.py` | Telegram alert delivery |
| `twag/renderer.py` | Markdown digest generation |
| `twag/tables.py` | Rich table formatting for CLI output |
| `twag/media.py` | Media handling utilities |
| `twag/link_utils.py` | URL expansion, embed classification |
| `twag/article_visuals.py` | Visual selection for X Articles |
| `twag/article_sections.py` | Article section extraction |
| `twag/text_utils.py` | Text processing utilities |
| `twag/metrics.py` | Lightweight in-memory metrics with optional SQLite flush |
| `twag/web/` | FastAPI backend + React feed UI (`web/frontend/`) |

## Data flow

```
bird CLI ── fetcher ──► storage ──► tweets (DB)
                          │
                          └── auto_promote_bookmarked_authors ──► accounts
                                                                    │
                          ┌──────── dependency BFS ──────────┐      │
                          ▼                                  │      │
process_unprocessed ── triage ── enrich ── article ── media ─┘  ─► tweets (DB updated)
                                                              │
                                                              └─► reactions, narratives
                                                                        │
                                                                        ▼
                                                                renderer ──► digest.md
                                                                notifier ──► Telegram
                                                                web      ──► /api/* + SPA
```

## Storage layout

twag follows XDG defaults (override with `TWAG_DATA_DIR`):

| Path | Purpose |
|------|---------|
| `~/.config/twag/config.json` | Configuration |
| `~/.local/share/twag/twag.db` | SQLite database |
| `~/.local/share/twag/digests/` | Generated digests |
| `~/.local/share/twag/following.txt` | Followed accounts |

See [database.md](./database.md) for the full schema.

## Web interface

`twag web` serves a FastAPI backend with a built React SPA. In dev mode
(`twag web --dev` or `TWAG_DEV=1`), the SPA is served by a separate Vite
dev server on port 8080 while FastAPI runs on the chosen port. CORS is
restricted to `localhost`/`127.0.0.1`. There is no authentication — bind
to localhost or a trusted network only. See [web-api.md](./web-api.md) for
the route reference.
