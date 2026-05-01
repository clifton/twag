# Test Coverage Gap Inventory

Snapshot taken on 2026-04-30 at branch `nightshift/test-gap-finder`.

Baseline coverage (before this PR): **66 %** total
(`uv run pytest --cov=twag --cov-report=term-missing`).
Coverage after the P0 tests added in this PR: **68 %** total. Per-module
deltas for the P0 rows are tabulated below.

This document enumerates every twag module whose direct unit-test coverage is
either zero or low (<60 %). For each module it records the rationale and a
suggested testing approach. Modules are grouped by priority. The PR that
introduces this file ships focused tests for the **P0** rows; other rows are
documented as follow-up work so they can be picked off incrementally.

## Priority key

- **P0** — pure-logic or security-adjacent code that drives credentials, config,
  scoring prompts, or persisted feedback. Easy to test, high blast radius if it
  regresses silently.
- **P1** — substantial logic but reachable only via heavier fixtures (network,
  filesystem, async LLM clients).
- **P2** — thin CLI/Click wrappers and FastAPI routes that are mostly
  glue. Worth integration tests via `CliRunner` / `TestClient` but not the best
  ROI for a first pass.

## P0 — pure-logic / security-adjacent (covered in this PR)

| Module | Before | After | Why it matters | Approach taken |
|--------|------:|------:|----------------|----------------|
| `twag/auth.py` | 76 % | 100 % | Parses `~/.env` and resolves API keys; security-adjacent. Branches for missing files, comments, `export` prefix, quoted values, and missing keys were all uncovered. | Pure functions over a `tmp_path` env file; monkeypatch `Path.home` and `os.environ`. |
| `twag/config.py` | 80 % | 100 % | Drives every runtime path (db, digests, following list) and merges user-supplied JSON onto defaults. Cache invalidation via mtime is subtle. | Drove `XDG_CONFIG_HOME`/`TWAG_DATA_DIR` via `monkeypatch.setenv` and wrote fake configs to `tmp_path`. Reset the module-level `_config_cache` between cases. |
| `twag/db/narratives.py` | 39 % | 100 % | Core CRUD for narrative tracking; upsert uses `ON CONFLICT` with mention-count increment that's hard to eyeball. | In-memory SQLite + the production schema fragment for `narratives` + `tweet_narratives`. Each public function gets happy path + a duplicate-link / sentiment-coalesce edge case. |
| `twag/db/prompts.py` | 33 % | 97 % | Stores LLM prompts and their version history — silent corruption here would change every triage/enrichment call. | In-memory SQLite + `prompts` / `prompt_history` tables. Covered seed, get, get-all, upsert (creates history), rollback, and unknown-version rollback. |
| `twag/db/context_commands.py` | 32 % | 95 % | Persists CLI templates that are later string-formatted into shell commands. Worth direct unit coverage so behavior is locked before any future shell-injection hardening lands. | In-memory SQLite + `context_commands` table; covered get/get_all/upsert/delete/toggle plus the COALESCE-preserve-description path. |

## P1 — heavier fixtures, follow-up

| Module | Baseline | Notes / suggested approach |
|--------|---------:|---------------------------|
| `twag/db/reactions.py` | 28 % | DB CRUD like the P0 rows, but `get_reactions_with_tweets` joins against `tweets`. Tests would need to seed both tables. Easy follow-up using the same in-memory pattern. |
| `twag/scorer/scoring.py` | 49 % | LLM orchestration. Pure helpers (prompt formatters, JSON parsing) can be lifted out and tested directly; the async LLM-calling paths would need an `AsyncMock` client. |
| `twag/scorer/llm_client.py` | 16 % | Thin `httpx`-driven adapter to Gemini/OpenAI. Test with `httpx.MockTransport` covering retries, 429 backoff, malformed JSON. |
| `twag/processor/storage.py` | 17 % | Glue between fetcher and DB. Useful tests would stub the fetcher and feed `Tweet` fixtures, asserting `_store_tweets` writes the expected rows. |
| `twag/processor/dependencies.py` | 61 % | Recursive quote/reply chain expansion. Deserves table-driven tests with stubbed fetchers; current coverage focuses on the storage call sites. |
| `twag/processor/triage.py` | 66 % | Largest module in the package. Helpers (batch grouping, deduplication, reaction-aware scoring) are good candidates for extraction + unit tests. |
| `twag/renderer.py` | 71 % | Markdown digest generation. Snapshot/golden-file tests around fixture tweets would lock current behavior cheaply. |
| `twag/notifier.py` | 80 % | Telegram delivery. The HTML-escape + chunking helpers are pure; `httpx.MockTransport` can cover the network paths. |
| `twag/db/connection.py` | 75 % | Most lines uncovered are `__getattr__` proxy methods on `Connection` — test via a thin smoke that exercises `commit`, `execute`, `__enter__`. |
| `twag/db/search.py` | 64 % | FTS5 query construction. Unit tests over the query-building helpers (without exercising real FTS) would lift coverage substantially. |
| `twag/db/tweets.py` | 72 % | Many uncovered branches are cursor-iteration variants. Add a few direct CRUD tests for the rarely-exercised filters (`bookmarked`, `signal_tier`). |

## P2 — CLI / web routes

| Module | Baseline | Notes |
|--------|---------:|-------|
| `twag/cli/init_cmd.py` | 9 % | First-run wizard. Worth a `CliRunner` happy-path test with `--non-interactive`. |
| `twag/cli/web.py` | 16 % | Just spawns uvicorn — coverage here will always be low; consider excluding from coverage gate. |
| `twag/cli/metrics_cmd.py` | 18 % | Pure formatting around `twag.metrics`; `CliRunner` with a seeded DB. |
| `twag/cli/fetch.py` | 28 % | Exercises real fetcher; integration test with monkeypatched bird CLI. |
| `twag/cli/db_cmd.py` | 30 % | DB shell/dump commands. `CliRunner` smoke tests are sufficient. |
| `twag/cli/stats.py` | 31 % | Reads from DB and prints Rich tables; seedable via the existing in-memory fixtures. |
| `twag/cli/narratives.py` | 36 % | Once `db/narratives` is unit-tested, a `CliRunner` smoke test here is easy. |
| `twag/cli/accounts.py` | 40 % | Largely Click wrappers around already-tested `db/accounts`. |
| `twag/cli/digest.py` | 47 % | Wraps `renderer.py`; gold-file based test covers both. |
| `twag/cli/config_cmd.py` | 44 % | Wraps `config.py`. |
| `twag/web/routes/*` | varies | Most are tested via `test_api_contracts.py` and `test_web_tweets_api.py`; `web/routes/context.py` and `web/routes/metrics.py` have no direct tests. |

## Modules already at strong coverage (≥85 %)

`twag/article_sections.py`, `twag/article_visuals.py`, `twag/cli/_progress.py`,
`twag/cli/analyze.py`, `twag/db/__init__.py`, `twag/db/accounts.py`,
`twag/db/alerts.py`, `twag/db/maintenance.py`, `twag/db/schema.py`,
`twag/db/time_utils.py`, `twag/fetcher/__init__.py`,
`twag/fetcher/extractors.py`, `twag/link_utils.py`, `twag/media.py`,
`twag/metrics.py`, `twag/scorer/prompts.py`, `twag/tables.py`,
`twag/text_utils.py`.

## Suggested next PRs

1. Lift the **P1 / db** rows (`db/reactions.py`, `db/connection.py`,
   `db/search.py`, `db/tweets.py`) using the same in-memory SQLite pattern
   established by the P0 PR.
2. Extract pure helpers from `processor/triage.py` and `scorer/scoring.py`,
   then unit-test them directly.
3. Add `httpx.MockTransport` coverage for `scorer/llm_client.py` and
   `notifier.py` HTTP paths.
4. Add `CliRunner` smoke tests for the **P2 / cli** rows in batches of three or
   four; most can share fixtures with the existing CLI status tests.
