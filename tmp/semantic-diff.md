# Semantic Diff: Commits dc4dbac..359e238

Analysis of the last 5 commits on `main`, explaining what changed, why it matters, and what to watch for.

---

## 1. `dc4dbac` — Enable and fix 10 new ruff lint rules (#33)

**What changed:** Ten new ruff lint rules were enabled across the project, touching 23 files. The rules enforce: performance patterns (PERF401 — list comprehensions instead of append loops), simplification (PLR5501 collapsible elif, PLR1730 use `max()`/`min()`, FURB188 use `removeprefix`/`removesuffix`), safety (PLW1510 — require explicit `check=False` on `subprocess.run`), hygiene (PIE — remove unnecessary `pass`/`else`, RET505 — unnecessary `else` after `return`), and type-checking discipline (TC003 — move type-only imports into `TYPE_CHECKING` blocks).

**Why it matters:** This is a code-quality baseline shift. The subprocess safety rule (PLW1510) is the most significant — it makes every `subprocess.run` call explicitly declare whether it cares about failures. The TYPE_CHECKING imports reduce runtime import overhead slightly.

**Behavioral impact:** None. All changes are mechanical refactors that preserve existing logic. No public API or CLI behavior changed.

**Risk:** Low. Pure refactoring under lint enforcement. The commit passed existing tests.

---

## 2. `04d7fe2` — Clarify and test owner-thread DB writes in processor executors (#88)

**What changed:** Added 276+ lines of parallelization tests (`tests/test_processor_parallelization.py`) that verify processor DB writes happen on the correct owner thread. Small annotations were added to `dependencies.py`, `pipeline.py`, and `triage.py` to clarify thread ownership.

**Why it matters:** The twag processor runs scoring and dependency resolution concurrently. Without guardrails, concurrent DB writes from the wrong thread could cause SQLite locking errors or data races. These tests codify the invariant that each executor writes only from its owning thread, making regressions detectable before they hit production.

**Behavioral impact:** None at runtime — this is a testing/documentation change. However, it significantly improves confidence in the processor's concurrency model and will catch future regressions in parallel processing paths.

**Risk:** Low. No production code paths changed. The tests themselves are additive.

---

## 3. `5ba10ef` — Enable FAST002 and PLR1714 ruff rules, fix 4 violations (#87)

**What changed:** Two more ruff rules were enabled. FAST002 converted 3 FastAPI `Query()` parameter declarations in `twag/web/routes/tweets.py` to the modern `Annotated[type, Query()]` style. PLR1714 merged repeated `!=` comparisons into a single `not in (...)` check.

**Why it matters:** The `Annotated` style is the recommended pattern in FastAPI v0.95+ and will be required in future versions. Adopting it now avoids a future migration. The PLR1714 fix is a readability improvement.

**Behavioral impact:** None. The FastAPI parameter declarations produce identical OpenAPI schemas and runtime behavior. The equality check refactor is logically equivalent.

**Risk:** Low. Trivial mechanical changes with no semantic effect.

---

## 4. `c5c036e` — Harden dependency ingestion and align single-tweet API contract (#89)

**What changed:** Two significant changes bundled in one commit:

1. **Dependency ingestion hardening** — The `bird read` pathway (`twag/fetcher/bird_cli.py`) gained structured failure classification via new `ReadTweetResult` and `ReadTweetFailure` dataclasses. Failures are now categorized as auth-related, transient/retryable, or permanent. The dependency processor (`twag/processor/dependencies.py`) uses these classifications to decide whether to retry or skip. The DB layer (`twag/db/tweets.py`, `twag/db/accounts.py`, `twag/db/connection.py`) received defensive improvements for handling malformed or missing dependency tweet data. A new `twag/text_utils.py` module was added.

2. **Single-tweet API contract alignment** — The `/tweets/{id}` endpoint was refactored so its response shape matches the `/tweets` list endpoint. Previously, fetching a single tweet returned a different field set than the same tweet appearing in a list response — causing frontend inconsistencies. New contract tests (`tests/test_api_contracts.py`, 272 lines) enforce this invariant. The frontend TypeScript types (`twag/web/frontend/src/api/types.ts`) were updated to match.

**Why it matters:** Dependency tweets (quoted tweets, replied-to tweets) are fetched from X on-demand during processing. Previously, a malformed response or transient X outage would log an error and silently skip the dependency with no structured way to retry later. Now failures are classified and surfaced with enough detail to enable retry logic and debugging. The API contract fix eliminates a class of frontend rendering bugs where single-tweet views displayed differently from list views.

**Behavioral impact:** Medium. API consumers of the single-tweet endpoint will see additional fields they weren't getting before (matching the list response). The dependency pipeline will handle X API failures more gracefully — fewer silent data losses, more informative log messages. The `read_tweet()` function's public signature is unchanged (still returns `Tweet | None`), but a new `read_tweet_with_diagnostics()` is available for callers that need failure details.

**Risk:** Medium. This is the highest-risk commit in the range. Data-path changes to dependency ingestion affect what gets stored in the DB. The API contract change could affect any frontend code that depended on the old single-tweet response shape (mitigated by the TypeScript type update and contract tests). The 1,144 lines added include substantial test coverage, which reduces risk.

---

## 5. `359e238` — Make process notifications opt-in (#94)

**What changed:** The `--notify/--no-notify` flag on `twag process` flipped its default from `True` to `False`. Previously, running `twag process` sent Telegram alerts for high-scoring tweets unless you passed `--no-notify`. Now notifications are silent by default; pass `--notify` to enable them. Documentation in `README.md`, `INSTALL.md`, and `SKILL.md` was updated. A new test file (`tests/test_cli_process_status.py`, 107 lines) verifies the flag behavior.

**Why it matters:** The old default meant every cron job or casual `twag process` run would fire Telegram alerts. This was noisy for users who run the pipeline frequently or during development/testing. Flipping to opt-in means alerts only fire when explicitly requested.

**Behavioral impact:** **Breaking change for existing cron jobs and scripts.** Any automation that relied on `twag process` sending notifications by default will silently stop alerting. Users must update their cron entries or wrapper scripts to include `--notify`. This is a one-line change but easy to miss if you don't read the changelog.

**Risk:** Low-Medium. The code change is trivial (one boolean flip), but the behavioral impact is high for users with existing automation. The risk is entirely in the deployment/communication layer, not the code itself.
