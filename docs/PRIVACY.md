# Privacy Policy

This document describes what data **twag** handles, where it goes, and how a user
controls it. Every claim below cites the module that enforces it so the policy
can be re-validated by spot-checking the cited files. The
[Consistency Checklist](#consistency-checklist) at the end is the audit map.

twag is a self-hosted CLI and local web UI. There is no twag-operated server,
account system, or hosted backend. Trust boundaries that matter:

- **The user's machine** — where the SQLite database, configuration, and
  credential files live.
- **`bird` CLI** — third-party tool that talks directly to x.com on the user's
  behalf using the user's session cookies.
- **LLM providers** (Google Gemini, optional Anthropic) — receive tweet text,
  embedded URLs, and (for vision calls) media bytes or URLs.
- **Telegram** — receives optional alert messages when configured.
- **Arbitrary external hosts** — receive HEAD/GET requests during `t.co` link
  expansion and image downloading for vision analysis.

twag has no analytics, no telemetry, and no ads.

---

## 1. Data Collected

twag does not solicit data from the user beyond the credentials they configure.
All other content is data the user has access to on x.com via their own
authenticated session.

### From the user

| Item | Where it comes from | Why |
|---|---|---|
| `AUTH_TOKEN`, `CT0` | env var or `~/.env` | Pass-through to `bird` for x.com auth |
| `GEMINI_API_KEY` | env var or `~/.env` | LLM scoring/enrichment |
| `ANTHROPIC_API_KEY` (optional) | env var or `~/.env` | Higher-quality enrichment |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (optional) | env var only | Alert delivery |
| Account list (`following.txt`, CLI) | user input | Tier-1 watch list |

Env-file parsing is in `twag/auth.py`. `load_env_file()` reads `~/.env` by
default and parses `KEY=value` lines (skipping blanks and comments, stripping
`export ` and surrounding quotes). `get_api_key()` checks `os.environ` first
and falls back to the env file.

### From x.com (via `bird`)

twag fetches tweets the user can already see while logged in. The bird CLI
returns parsed JSON; twag stores the fields it needs. Sources:

- Home timeline — `fetch_home_timeline` in `twag/fetcher/bird_cli.py`.
- A specific user's tweets — `fetch_user_tweets`.
- Search results — `fetch_search`.
- The user's own bookmarks — `fetch_bookmarks`. Read-only; twag never writes,
  deletes, or posts.
- Single tweet by URL/ID — `read_tweet`.

Stored tweet fields include the raw `content`, `author_handle`,
`author_name`, expanded URLs (`links_json`), media metadata (`media_items`),
quoted/retweeted source content, and X-native article bodies
(`article_text`). See the `tweets` table in `twag/db/schema.py`.

---

## 2. Local Storage

All persistent twag state lives on the user's machine in SQLite and a few
plaintext files. No twag-operated cloud storage exists.

### Locations

Resolved by `get_data_dir()` in `twag/config.py`:

1. `TWAG_DATA_DIR` env var, if set.
2. `paths.data_dir` in `~/.config/twag/config.json`.
3. XDG default: `~/.local/share/twag/`.

Within that directory:

- `twag.db` — primary SQLite database (`get_database_path` in `twag/config.py`).
- `digests/` — generated markdown digests (`get_digests_dir`).
- `following.txt` — followed-account list (`get_following_path`).

Configuration lives at `$XDG_CONFIG_HOME/twag/config.json` (default
`~/.config/twag/config.json`).

### Tables

Defined in `twag/db/schema.py`. All tables are local-only:

| Table | Contains |
|---|---|
| `tweets` | Fetched tweets: content, author handle/name, expanded links, media items, article text, retweet/quote source content. |
| `accounts` | Watch list: handle, display name, tier, scoring stats. |
| `narratives`, `tweet_narratives` | LLM-detected themes and tweet links. No personal data beyond topic strings. |
| `reactions` | User feedback per tweet: reaction type, optional free-text reason, target. |
| `prompts`, `prompt_history` | Editable LLM prompt templates and version history. |
| `context_commands` | User-defined CLI command templates for context enrichment. |
| `fetch_log` | Endpoint, fetch counts, query params (no message bodies). |
| `alert_log` | `tweet_id` and `chat_id` only. **Message bodies are not stored.** Persisted by `log_alert` in `twag/db/alerts.py`; written from `send_telegram_alert` in `twag/notifier.py`. |
| `metrics` | Internal counters (request counts, latency). No personal data. |

---

## 3. Third-Party Services

twag's outbound network surface is limited to the call sites below.
Comprehensive: a project-wide search for `httpx`, `requests`, `urllib.request`,
and `aiohttp` finds exactly three direct call sites in production code (LLM
providers are reached through their vendor SDKs):

| Site | Destination |
|---|---|
| `_call_gemini_vision` in `twag/scorer/llm_client.py` (`httpx.get`) | Image host (typically `pbs.twimg.com`) |
| `send_telegram_alert` in `twag/notifier.py` (`httpx.post`) | `api.telegram.org` |
| `_expand_short_url` in `twag/link_utils.py` (`httpx.request`) | Whatever `t.co` redirects to |

### 3.1 Google Gemini

SDK: `google-genai`. Endpoint: `generativelanguage.googleapis.com`.

- **Text calls** (`_call_gemini` in `twag/scorer/llm_client.py`) — send a single
  prompt string. The prompts in `twag/scorer/prompts.py` (`TRIAGE_PROMPT`,
  `BATCH_TRIAGE_PROMPT`, `ENRICHMENT_PROMPT`, `SUMMARIZE_PROMPT`,
  `DOCUMENT_SUMMARY_PROMPT`, `ARTICLE_SUMMARY_PROMPT`) embed tweet text,
  author handle, quoted-tweet text, linked-article summaries, and media
  descriptions before the request.
- **Vision calls** (`_call_gemini_vision`) — twag downloads the image with
  `httpx.get` (timeout 30s), then uploads the raw bytes to Gemini alongside the
  prompt. So vision enables a second outbound request to the original media
  host.

### 3.2 Anthropic (optional)

SDK: `anthropic`. Endpoint: `api.anthropic.com`.

- **Text calls** (`_call_anthropic` in `twag/scorer/llm_client.py`) — send the
  same prompts as Gemini text calls.
- **Vision calls** (`_call_anthropic_vision`) — pass an `{"type": "image",
  "source": {"type": "url", "url": image_url}}` block. Anthropic's servers
  fetch the image directly; twag does not download the image first on this
  path.

Anthropic is engaged only when the user sets `ANTHROPIC_API_KEY` and selects an
Anthropic model in `config.json` (`llm.enrichment_provider`).

### 3.3 Telegram (optional)

`send_telegram_alert` in `twag/notifier.py` POSTs to
`https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage` with:

- `chat_id`
- `text` — formatted by `format_alert`. Contains the author handle, a
  150-character preview of the tweet content, the LLM summary, ticker symbols,
  and the tweet URL.
- `parse_mode: "HTML"`, `disable_web_page_preview: false`.

Alerts are off unless both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set
and `notifications.telegram_enabled` is true. Quiet hours and a per-hour rate
limit are enforced by `can_send_alert` (`twag/notifier.py`); rate-limit state
comes from the `alert_log` table via `get_recent_alert_count`.

### 3.4 x.com (via `bird`)

twag does not make direct HTTP requests to x.com. All x.com traffic is issued
by the third-party `bird` subprocess. `run_bird` in
`twag/fetcher/bird_cli.py` builds the command line with the user's
`AUTH_TOKEN` and `CT0` and runs it via `subprocess.run`.

Auth tokens are passed as `--auth-token` and `--ct0` CLI flags rather than env
vars. This means the values are visible in `/proc/<pid>/cmdline` for processes
the user can already see. The trade-off is documented inline in
`twag/fetcher/bird_cli.py` and is acceptable for a single-user local tool. It
will be revisited if `bird` adds env-var auth support.

### 3.5 Arbitrary external hosts (link expansion)

`_expand_short_url` in `twag/link_utils.py` resolves `t.co` short URLs by
issuing `HEAD` (1.0s timeout) then a fallback `GET` (1.5s timeout) with
`follow_redirects=True`. The `User-Agent` header is
`twag/1.0 (+https://github.com/clifton/twag)`. Caps:

- `_MAX_SHORT_URL_EXPANSIONS = 2` per tweet.
- `_MAX_NETWORK_EXPANSION_ATTEMPTS = 512` total per process.
- Only hosts in `_SHORTENER_DOMAINS = {"t.co"}` are fetched; other URLs are
  used as-is.

The expansion target is the host x.com chose to redirect to — in practice,
publishers cited from tweets. Those hosts see a request from the user's IP.

### 3.6 Image hosts (vision pipeline)

When Gemini vision is enabled, `_call_gemini_vision` fetches the image bytes
directly via `httpx.get(image_url, timeout=30)` before uploading to Gemini.
Image URLs come from the tweet's media attachments. Those hosts see a request
from the user's IP.

When Anthropic vision is used, the image URL is forwarded by reference, so
Anthropic's servers — not the user — fetch it.

---

## 4. Credentials & Secrets

### How they're read

- `get_api_key(name)` in `twag/auth.py` checks `os.environ`, then
  `~/.env` via `load_env_file()`, and raises if missing. Used for
  `GEMINI_API_KEY` and `ANTHROPIC_API_KEY` (`twag/scorer/llm_client.py`).
- `get_auth_env()` in `twag/auth.py` returns `os.environ` merged with `~/.env`
  for the `bird` subprocess.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are read directly from
  `os.environ` in `twag/notifier.py`. They are **not** routed through the
  `~/.env` fallback. If unset, `send_telegram_alert` returns `False` silently.

### How they're protected in logs

- `_redact_stderr` in `twag/fetcher/bird_cli.py` strips the values of
  `_SENSITIVE_ENV_VARS = ("AUTH_TOKEN", "CT0", "GEMINI_API_KEY",
  "ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN")` from `bird`'s stderr before
  logging, then scrubs hex strings of length ≥32 (`<redacted-hex>`).
- `twag/notifier.py` only logs at `WARNING` level, only on infrastructure
  failures, and never logs the bot token, chat ID values, or message content.
  The `chat_id` is persisted to `alert_log` (with the `tweet_id`); the bot
  token is never persisted.
- `twag/scorer/llm_client.py` has no logging statements. API keys are passed
  directly to `Anthropic(api_key=...)` and `genai.Client(api_key=...)` and are
  not echoed.

### Where they're stored

twag does not write credentials to disk. The user's `~/.env` file (if used) is
the only place credentials live, and twag does not modify it.

---

## 5. Retention & Deletion

twag does not run any automatic background pruning. The user controls
retention.

- `twag prune --days N` (`twag/cli/stats.py`) deletes tweets older than `N`
  days **only if** they have been included in a digest
  (`included_in_digest IS NOT NULL`). Implementation in
  `prune_old_tweets` in `twag/db/maintenance.py`. Unprocessed or
  un-distributed tweets are never auto-pruned. `--dry-run` previews without
  deleting. Stale narratives older than 7 days are archived in the same
  command.
- `twag db dump [--stdout]` (`twag/cli/db_cmd.py`) writes a SQL dump for
  backup.
- `twag db restore <file> [--force]` replaces the database, automatically
  backing up the existing `twag.db` to `twag.db.bak` first.
- `twag db shell` opens an interactive `sqlite3` shell for direct inspection
  or deletion.
- `twag db init` re-initializes the schema.

To delete everything, remove the data directory (default
`~/.local/share/twag/`).

---

## 6. User Controls

- **Disable Telegram alerts** — leave `TELEGRAM_BOT_TOKEN` /
  `TELEGRAM_CHAT_ID` unset, or set `notifications.telegram_enabled = false`
  in `config.json`. `can_send_alert` in `twag/notifier.py` short-circuits
  when disabled.
- **Quiet hours** — `notifications.quiet_hours_start` and
  `notifications.quiet_hours_end` in `config.json` block alerts in a window
  (overridden only by score-10 tweets).
- **Per-hour alert cap** — `notifications.max_alerts_per_hour`.
- **Disable Anthropic** — leave `ANTHROPIC_API_KEY` unset and use only
  Gemini-backed `llm.*` providers.
- **Move data dir** — set `TWAG_DATA_DIR` or `paths.data_dir` (`twag/config.py`).
- **Mute / demote authors** — `twag accounts mute <handle>`, `demote`, etc.
  (`twag/db/accounts.py`).

---

## 7. Out of Scope

- **No analytics, telemetry, or third-party tracking.** A grep of the frontend
  for `analytics`, `telemetry`, `gtag`, `mixpanel`, `segment`, `amplitude`,
  `plausible`, and `pixel` returns zero matches. The `twag/metrics.py` module
  is purely in-process counters with optional SQLite flush; nothing leaves the
  machine.
- **Web UI is local-only.** `twag/web/app.py` mounts CORS with
  `allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"`. The
  default web bind is `localhost`. `app.state.db_path` points at the local
  SQLite file and routes use read-only connections (e.g. `twag/web/routes/tweets.py`).
  The web UI has no authentication; bind it only to localhost or trusted
  networks (already documented in `README.md`).
- **No supply-chain auto-updates.** twag does not self-update.

---

## Consistency Checklist

Each row maps a policy claim to the file that enforces it. To re-validate the
policy, spot-check the cited file and confirm the behavior described still
holds. If a row drifts, update both the code and this row.

| Claim | Enforced by |
|---|---|
| Env vars and `~/.env` are the only credential sources | `twag/auth.py` (`load_env_file`, `get_api_key`, `get_auth_env`) |
| Auth tokens passed to `bird` as CLI flags (visible in `/proc`) | `twag/fetcher/bird_cli.py` (`run_bird`, comment block above the `--auth-token` extension) |
| `bird` stderr is redacted before logging | `twag/fetcher/bird_cli.py` (`_redact_stderr`, `_SENSITIVE_ENV_VARS`) |
| Bookmarks fetch is read-only | `twag/fetcher/bird_cli.py` (`fetch_bookmarks` calls only `bird bookmarks ... --json`) |
| All tweet data lives in local SQLite | `twag/db/schema.py` (`tweets` table) |
| Database path resolution: `TWAG_DATA_DIR` → `config.json` → XDG | `twag/config.py` (`get_data_dir`, `get_database_path`) |
| `alert_log` stores `tweet_id` + `chat_id` only, no message body | `twag/db/alerts.py` (`log_alert`); call site `twag/notifier.py` (`send_telegram_alert`) |
| Pruning is user-invoked and only touches digested tweets | `twag/cli/stats.py` (`prune` command); `twag/db/maintenance.py` (`prune_old_tweets`) |
| Outbound HTTP is limited to three sites in production code | `twag/scorer/llm_client.py` (`_call_gemini_vision`), `twag/notifier.py` (`send_telegram_alert`), `twag/link_utils.py` (`_expand_short_url`) |
| LLM prompts contain user-facing tweet content | `twag/scorer/prompts.py` (all `*_PROMPT` templates) |
| Gemini vision downloads images server-side then uploads bytes | `twag/scorer/llm_client.py` (`_call_gemini_vision`) |
| Anthropic vision passes the image URL by reference | `twag/scorer/llm_client.py` (`_call_anthropic_vision`) |
| Telegram message body contains author handle, 150-char preview, summary, tickers, tweet URL | `twag/notifier.py` (`format_alert`) |
| Telegram off when keys missing or `telegram_enabled = false` | `twag/notifier.py` (`can_send_alert`, `send_telegram_alert` early returns) |
| Alert quiet hours and per-hour rate limit enforced | `twag/notifier.py` (`is_quiet_hours`, `can_send_alert`); `twag/db/alerts.py` (`get_recent_alert_count`) |
| Link expansion limited to `t.co` and capped per tweet/process | `twag/link_utils.py` (`_SHORTENER_DOMAINS`, `_MAX_SHORT_URL_EXPANSIONS`, `_MAX_NETWORK_EXPANSION_ATTEMPTS`, `_expand_short_url`) |
| Web UI CORS limited to localhost | `twag/web/app.py` (`allow_origin_regex`) |
| Web routes use read-only DB connections | `twag/web/routes/tweets.py` (`get_connection(db_path, readonly=True)`) |
| No analytics/telemetry beacons | grep across `twag/web/frontend/` for known vendors returns zero matches |
| `twag/metrics.py` is in-process only | `twag/metrics.py` (`MetricsCollector`, `flush_to_db` — local SQLite only) |
