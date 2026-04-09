# Semantic Diff Explainer — `td-review/fixes-2026-04-03`

**Branch:** `td-review/fixes-2026-04-03` (1 commit: `c5a5117`)
**Base:** `main`
**Files changed:** 5 | **Lines:** +93 / −10

---

## Change Themes

### 1. httpx Migration in URL Expansion (`twag/link_utils.py`)

**Intent:** Replace `urllib.request` (stdlib) with `httpx` for short-URL expansion in `_expand_short_url`.

**What changed:**
- Removed `from urllib.request import Request, urlopen`; added `import httpx`
- Replaced `Request` + `urlopen` with `httpx.request(method, url, headers=..., timeout=..., follow_redirects=True)`
- Response URL accessed via `str(response.url)` instead of `response.geturl()`

**Semantic impact:** Positive. `httpx` is already a project dependency (used in notifier and web client code), so this unifies the HTTP stack. `follow_redirects=True` explicitly enables redirect following, which was implicit with `urlopen`. The error handling (`except Exception: continue`) is preserved, maintaining the same fallback behavior.

**Verdict:** ✅ Correct — consolidates HTTP library usage with no behavioral regression.

---

### 2. Notifier Logging Fix (`twag/notifier.py`)

**Intent:** Restore observability to the `send_telegram_alert` exception handler.

**What changed:**
- Added `log.warning("Telegram send failed", exc_info=True)` inside the bare `except Exception` block that previously silently returned `False`.

**Semantic impact:** This is a P0-level fix. The previous code swallowed all exceptions without any trace, making Telegram delivery failures invisible. The `exc_info=True` parameter ensures the full traceback is captured in logs, enabling diagnosis of network errors, auth failures, or API changes.

**Verdict:** ✅ Correct — restores observability without changing control flow. The function still returns `False` on failure, so callers are unaffected.

---

### 3. Type Hints for `_with_retry` (`twag/scorer/llm_client.py`)

**Intent:** Add generic type annotations to the retry wrapper function.

**What changed:**
- Added `from collections.abc import Callable` and `from typing import TypeVar`
- Defined `_T = TypeVar("_T")`
- Changed signature from `def _with_retry(fn)` to `def _with_retry(fn: Callable[[], _T]) -> _T`

**Semantic impact:** Pure type-level change — no runtime behavior change. The annotation correctly expresses that `_with_retry` preserves the return type of the wrapped callable. This enables downstream type checkers to infer return types through the retry wrapper.

**Verdict:** ✅ Correct — improves type safety with zero runtime risk.

---

### 4. New Tests for httpx Migration (`tests/test_link_utils.py`)

**Intent:** Validate that `_expand_short_url` works correctly with the new `httpx` backend.

**Tests added:**
- `test_expand_short_url_uses_httpx` — Mocks `httpx.request` to return a redirect target, asserts the expanded URL is returned. Verifies the httpx integration path works.
- `test_expand_short_url_falls_back_on_httpx_error` — Mocks `httpx.request` to raise `httpx.ConnectError`, asserts the original URL is returned unchanged. Verifies graceful degradation.

Both tests properly clear the `lru_cache` before and after execution and reset the network expansion attempt counter.

**Verdict:** ✅ Correct — good coverage of happy path and error path for the httpx migration.

---

### 5. New Tests for Notifier Logging (`tests/test_notifier.py`)

**Intent:** Validate `send_telegram_alert` behavior on success and failure.

**Tests added:**
- `test_send_telegram_alert_logs_on_exception` — Mocks `httpx.post` to raise `ConnectError`, captures log output, asserts `"Telegram send failed"` appears in logs and function returns `False`. Directly validates the P0-3 logging fix.
- `test_send_telegram_alert_returns_true_on_success` — Mocks `httpx.post` to return a 200 response, asserts function returns `True`. Validates the happy path.

**Verdict:** ✅ Correct — tests directly cover the notifier logging fix and confirm existing success behavior.

---

## Summary

| # | Theme | Files | Verdict |
|---|-------|-------|---------|
| 1 | httpx migration | `twag/link_utils.py` | ✅ Correct |
| 2 | Notifier logging fix | `twag/notifier.py` | ✅ Correct |
| 3 | Type hints | `twag/scorer/llm_client.py` | ✅ Correct |
| 4 | httpx migration tests | `tests/test_link_utils.py` | ✅ Correct |
| 5 | Notifier logging tests | `tests/test_notifier.py` | ✅ Correct |

**No regressions found.** All changes are additive improvements: unified HTTP stack, restored observability, improved type safety, and new test coverage.
