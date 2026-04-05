# Knowledge Silo Analysis Report

**Repository:** twag  
**Date:** 2026-04-04  
**Total commits:** 72  
**Total Python source files:** 68 (in `twag/`)  
**Total source lines:** 12,421  
**Bus factor:** 1

---

## Executive Summary

This is a **single-contributor project** — 100% of code is authored by Clifton King across all 72 commits. By definition, the entire codebase is a knowledge silo. Every module carries bus-factor-1 risk.

The analysis below ranks modules by a **risk score** (lines x churn x test penalty) to identify where knowledge loss would cause the most damage. Of 68 source modules, **50 have no dedicated test coverage**, concentrating risk in the scorer, database, web route, and CLI layers.

---

## Top Risk Areas

Risk score = `lines x commits x test_penalty` where test_penalty = **2.0** (no tests) or **1.0** (has tests).

| Rank | Module | Lines | Commits | Tests? | Risk Score |
|-----:|--------|------:|--------:|--------|------------|
| 1 | `twag/web/routes/tweets.py` | 639 | 14 | Yes | 8,946 |
| 2 | `twag/processor/triage.py` | 829 | 5 | Partial | 4,145 |
| 3 | `twag/web/routes/context.py` | 410 | 4 | **No** | **3,280** |
| 4 | `twag/renderer.py` | 344 | 8 | Yes | 2,752 |
| 5 | `twag/config.py` | 178 | 7 | **No** | **2,492** |
| 6 | `twag/db/tweets.py` | 803 | 3 | Partial | 2,409 |
| 7 | `twag/fetcher/bird_cli.py` | 381 | 6 | Yes | 2,286 |
| 8 | `twag/processor/dependencies.py` | 538 | 4 | Partial | 2,152 |
| 9 | `twag/fetcher/extractors.py` | 513 | 4 | Yes | 2,052 |
| 10 | `twag/link_utils.py` | 334 | 6 | Yes | 2,004 |
| 11 | `twag/web/routes/prompts.py` | 278 | 3 | **No** | **1,668** |
| 12 | `twag/processor/pipeline.py` | 413 | 3 | Partial | 1,239 |
| 13 | `twag/web/routes/reactions.py` | 186 | 3 | **No** | **1,116** |
| 14 | `twag/db/search.py` | 491 | 1 | **No** | **982** |
| 15 | `twag/scorer/scoring.py` | 393 | 1 | **No** | **786** |

**Key insight:** `web/routes/tweets.py` has the highest absolute risk due to 14 commits (highest churn in the codebase) despite having tests. The untested modules `web/routes/context.py`, `config.py`, and `web/routes/prompts.py` rank highly because churn + no tests compounds risk.

---

## Test Coverage Gap Analysis

### Modules WITH dedicated tests (18 modules covered)

| Test File | Covers |
|-----------|--------|
| `test_api_contracts.py` | `models/api.py` |
| `test_article_processing.py` | Article processing pipeline |
| `test_article_sections.py` | `article_sections.py` |
| `test_article_visuals.py` | `article_visuals.py` |
| `test_cli_analyze_status.py` | `cli/analyze.py` |
| `test_cli_fetch_status.py` | `cli/fetch.py` |
| `test_cli_process_status.py` | `cli/process.py` |
| `test_cli_search.py` | `cli/search.py` |
| `test_db_dump_restore.py` | `db/` (dump/restore paths) |
| `test_db_retweet_backfill.py` | `db/tweets.py` (partial) |
| `test_fetcher.py` | `fetcher/bird_cli.py`, `fetcher/extractors.py` |
| `test_link_utils.py` | `link_utils.py` |
| `test_processor.py` | `processor/` (pipeline, storage, triage) |
| `test_processor_parallelization.py` | `processor/` (parallel execution) |
| `test_renderer_article_sections.py` | `renderer.py` (article sections) |
| `test_renderer_links.py` | `renderer.py` (link rendering) |
| `test_tables.py` | `tables.py` |
| `test_web_tweets_api.py` | `web/routes/tweets.py` |

### Modules WITHOUT any dedicated tests (50 modules)

Grouped by package, sorted by risk:

**Scorer (4 files, 803 lines total — completely untested)**
- `scorer/scoring.py` (393 lines) — core LLM scoring logic
- `scorer/llm_client.py` (229 lines) — LLM client management
- `scorer/prompts.py` (136 lines) — scoring prompt templates
- `scorer/__init__.py` (45 lines)

**Database (9 untested files, 2,108 lines)**
- `db/search.py` (491 lines) — full-text search
- `db/connection.py` (261 lines) — connection management
- `db/prompts.py` (234 lines) — prompt storage
- `db/schema.py` (208 lines) — schema definitions
- `db/maintenance.py` (189 lines) — database maintenance
- `db/accounts.py` (176 lines) — account management
- `db/reactions.py` (137 lines) — reaction storage
- `db/time_utils.py` (126 lines) — time utilities
- `db/context_commands.py` (111 lines) — context commands

**Web (5 untested files, 849 lines)**
- `web/routes/context.py` (410 lines) — context routes
- `web/routes/prompts.py` (278 lines) — prompt routes
- `web/routes/reactions.py` (186 lines) — reaction routes
- `web/tweet_utils.py` (82 lines) — tweet utilities
- `web/app.py` (74 lines) — FastAPI app setup

**CLI (8 untested files, 671 lines)**
- `cli/init_cmd.py` (213 lines) — init command
- `cli/accounts.py` (148 lines) — account commands
- `cli/db_cmd.py` (147 lines) — database commands
- `cli/web.py` (107 lines) — web server command
- `cli/stats.py` (104 lines) — stats command
- `cli/_progress.py` (79 lines) — progress display
- `cli/config_cmd.py` (55 lines) — config command
- `cli/digest.py` (36 lines) — digest command

**Other (7 untested files, 557 lines)**
- `config.py` (178 lines) — runtime configuration
- `notifier.py` (171 lines) — Telegram notifications
- `media.py` (79 lines) — media handling
- `auth.py` (53 lines) — authentication/credentials
- `text_utils.py` (38 lines) — text utilities
- `db/narratives.py` (71 lines)
- `cli/narratives.py` (35 lines)

**Models (7 untested files, 420 lines)** — lower risk as data models
- `models/db_models.py` (102 lines)
- `models/config.py` (97 lines)
- `models/__init__.py` (87 lines)
- `models/scoring.py` (84 lines)
- `models/tweet.py` (42 lines)
- `models/media.py` (37 lines)
- `models/links.py` (36 lines)

---

## Recommendations

### Priority 1 — High Risk, High Impact

These modules are large, frequently changed, and lack tests:

1. **`web/routes/context.py`** (410 lines, 4 commits, untested) — Add API contract tests similar to `test_web_tweets_api.py`
2. **`config.py`** (178 lines, 7 commits, untested) — High churn config module; test default resolution and override behavior
3. **`scorer/scoring.py`** (393 lines, untested) — Core scoring logic with zero test coverage; mock LLM responses and test scoring pipeline

### Priority 2 — Large Untested Modules

4. **`db/search.py`** (491 lines, untested) — Full-text search is complex; add integration tests
5. **`web/routes/prompts.py`** (278 lines, 3 commits, untested) — Active endpoint with no coverage
6. **`db/connection.py`** (261 lines, untested) — Foundation layer; failures here cascade everywhere
7. **`scorer/llm_client.py`** (229 lines, untested) — Client management and retry logic

### Priority 3 — Documentation as Mitigation

For modules where testing is difficult (Telegram integration, CLI commands with side effects):

8. **`notifier.py`** — Document the Telegram API contract and expected message formats
9. **`cli/init_cmd.py`** — Document the initialization flow and expected state transitions
10. **`db/schema.py`** — Document migration strategy and schema evolution rules

### General Mitigations

- **Bus factor = 1 across the entire codebase.** The single most effective mitigation is onboarding a second contributor with commit access and context on the scoring and processing pipelines.
- **50 of 68 source modules lack tests.** Prioritize test coverage for the scorer and database layers, as these are the hardest to understand from code alone.
- **Web routes have the highest churn.** The 14-commit frequency on `web/routes/tweets.py` suggests this is the most actively evolving area — maintain test coverage here as it grows.

---

## Methodology

- **Source files:** All `.py` files under `twag/` (68 files, 12,421 lines)
- **Churn:** Number of commits touching each file (`git log --oneline <file> | wc -l`)
- **Test mapping:** Manual mapping of `tests/test_*.py` files to source modules
- **Risk score:** `lines x commits x test_penalty` (2.0 if untested, 1.0 if tested)
- **Author analysis:** `git log --format='%aN' | sort -u` confirms single contributor
