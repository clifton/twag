# Web API reference

FastAPI backend for the React feed UI. The app is created in
[`twag/web/app.py`](../twag/web/app.py); routers live under
[`twag/web/routes/`](../twag/web/routes/) and are mounted with the `/api`
prefix.

## Conventions

- All routes are under `/api`.
- Responses are JSON.
- CORS is restricted to `localhost`/`127.0.0.1` origins.
- Request and response latency is captured by middleware as
  `web.requests` (counter) and `web.request_latency_seconds` (histogram).
- There is **no authentication**. Bind to localhost only.

## Health and metrics

### `GET /api/health`

Service health: uptime, version, database connectivity.

Response:

```json
{
  "status": "ok" | "degraded",
  "version": "string",
  "uptime_seconds": 0.0,
  "db_connected": true
}
```

### `GET /api/metrics`

Snapshot of the in-memory metrics collector — counters, gauges,
histograms, and which subsystems have recorded at least one metric. See
[metrics.md](./metrics.md).

## Tweets (`tweets.py`)

### `GET /api/tweets`

Paginated feed of processed tweets.

| Param | Type | Default | Purpose |
|-------|------|---------|---------|
| `category` | str | — | Category filter (`fed_policy`, `equities`, …) |
| `ticker` | str | — | Ticker symbol filter |
| `min_score` | float (0–10) | — | Minimum relevance score |
| `signal_tier` | str | — | `high_signal`, `market_relevant`, `news`, `noise` |
| `author` | str | — | Author handle filter |
| `bookmarked` | bool | `false` | Only bookmarked tweets |
| `since` | str | — | `today`, `7d`, `2026-01-15`, … |
| `until` | str | — | `YYYY-MM-DD` |
| `sort` | str | `relevance` | Sort order |
| `limit` | int 1–200 | 50 | Page size |
| `offset` | int ≥ 0 | 0 | Pagination offset |

Response: `{"tweets": [...], "offset", "limit", "count", "has_more"}`.

Each tweet object includes (non-exhaustive): `id`, `author_handle`,
`author_name`, `display_*`, `content`, `content_summary`, `summary`,
`created_at`, `relevance_score`, `categories`, `signal_tier`, `tickers`,
`bookmarked`, `has_quote`, `quote_tweet_id`, `has_media`,
`media_analysis`, `media_items`, `has_link`, `link_summary`,
`is_x_article`, `article_*`, `is_retweet`, `retweeted_by_*`,
`original_*`, `reactions`, `quote_embed`, `inline_quote_embeds`,
`reference_links`, `external_links`, `display_content`.

### `GET /api/tweets/{tweet_id}`

A single tweet with the same enriched display fields as the list
endpoint. Returns `{"error": "Tweet not found"}` on miss.

### `GET /api/categories`

All categories with tweet counts, sorted by count descending.

```json
{"categories": [{"name": "fed_policy", "count": 42}, ...]}
```

### `GET /api/tickers`

Mentioned tickers with counts. `limit` (default 50) caps the result.

```json
{"tickers": [{"symbol": "NVDA", "count": 17}, ...]}
```

## Reactions (`reactions.py`)

### `POST /api/react`

Create a reaction. Body (`ReactionCreate`):

| Field | Type | Purpose |
|-------|------|---------|
| `tweet_id` | str | Tweet being reacted to |
| `reaction_type` | str | `>>`, `>`, `<`, `x_author`, `x_topic` |
| `reason` | str? | Optional free-text |
| `target` | str? | Author handle (`x_author`) or category (`x_topic`) |

Standard response: `{"id", "tweet_id", "reaction_type"}`. The `x_author`
type also mutes the account and returns `{"id", "message"}`.

### `GET /api/reactions/{tweet_id}`

All reactions for a tweet:

```json
{"tweet_id": "...", "reactions": [{"id", "reaction_type", "reason", "target", "created_at"}, ...]}
```

### `DELETE /api/reactions/{reaction_id}`

Delete a reaction. Returns `{"message": "Reaction deleted"}` or
`{"error": "Reaction not found"}`.

### `GET /api/reactions/summary`

`{"summary": <counts by type>}`.

### `GET /api/reactions/export`

Reactions joined to tweet data, useful for prompt-tuning analysis.

| Param | Type | Default | Purpose |
|-------|------|---------|---------|
| `reaction_type` | str | — | Filter to a single type |
| `limit` | int | 100 | Max results |

Response: `{"count", "reactions": [{"reaction": {...}, "tweet": {...}}, ...]}`
where `tweet.content` is truncated to 500 chars.

## Prompts (`prompts.py`)

### `GET /api/prompts`

All editable prompts.

```json
{"prompts": [{"id", "name", "template", "version", "updated_at", "updated_by"}, ...]}
```

### `GET /api/prompts/{name}`

A single prompt or `{"error": "Prompt not found"}`.

### `PUT /api/prompts/{name}`

Update a prompt. Body (`PromptUpdate`):

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `template` | str | — | New template body |
| `updated_by` | str | `user` | Attribution string |

Response: `{"name", "version", "message": "Prompt updated"}`.

### `GET /api/prompts/{name}/history`

Prior versions; `limit` (default 10) caps the count.

### `POST /api/prompts/{name}/rollback`

Roll back a prompt to a specific version. Query: `version: int`.

### `POST /api/prompts/tune`

LLM-assisted prompt tuning based on user reactions. Body (`TuneRequest`):

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `prompt_name` | str | — | Prompt to tune |
| `reaction_limit` | int | 50 | Max reactions analyzed per type |

Response: `{"prompt_name", "current_version", "analysis", "suggested_prompt", "reactions_analyzed": {"high_importance", "should_be_higher", "less_important"}}`.

### `POST /api/prompts/{name}/apply-suggestion`

Apply an LLM suggestion. Body matches `PromptUpdate`; `updated_by` is
forced to `"llm"`. Response: `{"name", "version", "message": "LLM suggestion applied"}`.

## Context commands (`context.py`)

Allowlisted shell commands the web UI can run during deep-analyze.

**Allowed base commands:** `bird`, `cat`, `echo`, `grep`, `head`, `jq`,
`rg`, `sed`, `tail`, `twag`, `wc`.

**Forbidden metacharacters:** `;`, `|`, `&`, `` ` ``, `$`, `>`, `<`,
newline.

**Template variables:** `{tweet_id}`, `{author}`, `{tweet_date}`,
`{tweet_datetime}`, `{ticker}`, `{tickers}`.

### `GET /api/context-commands`

| Param | Type | Default | Purpose |
|-------|------|---------|---------|
| `enabled_only` | bool | `false` | Return only enabled commands |

Response: `{"commands": [{"id", "name", "command_template", "description", "enabled", "created_at"}, ...]}`.

### `POST /api/context-commands`

Create a command. Body (`ContextCommandCreate`):

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `name` | str | — | Unique command name |
| `command_template` | str | — | Shell template with `{var}` placeholders |
| `description` | str? | — | Human-readable description |
| `enabled` | bool | `true` | Whether the command is active |

Validates allowlist + forbidden metacharacters.

### `GET /api/context-commands/{name}`

Single command or `{"error": "Context command not found"}`.

### `PUT /api/context-commands/{name}`

Update a command (same body schema as create, same validation).

### `DELETE /api/context-commands/{name}`

Delete a command.

### `POST /api/context-commands/{name}/toggle`

Query: `enabled: bool`.

### `POST /api/context-commands/{name}/test`

Substitute tweet variables and run the command (30 s timeout). Body:
`{"tweet_id": str}`.

Response: `{"command_name", "command_template", "final_command", "variables_used", "stdout", "stderr", "returncode", "success"}`.

### `POST /api/analyze/{tweet_id}`

Deep-analyze a tweet by running all enabled context commands and
injecting their output into an analysis prompt. No request body.

Response: `{"tweet_id", "author", "content" (truncated to 500 chars), "original_score", "original_tier", "context_commands_run", "context_data", "analysis"}`.

## Frontend serving

In production, FastAPI serves the built React SPA from
`twag/web/frontend/dist`:

- `GET /assets/...` — static assets (mounted via `StaticFiles`).
- `GET /{full_path:path}` — SPA catch-all that returns `index.html` for
  any non-API path.

In dev mode (`twag web --dev` or `TWAG_DEV=1`), the SPA is served by Vite
on port 8080 and the catch-all is disabled.
