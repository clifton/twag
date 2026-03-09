# Privacy Policy

Last updated: 2026-03-08

twag is a **local-first** Twitter/X market signal aggregator. It runs on your
machine, stores data locally, and exposes a web interface only on `localhost`.

---

## Data Collected

twag fetches and stores the following from Twitter/X via the `bird` CLI:

- **Tweet content** — full text, quoted text, article body text
- **Author information** — handles (`@username`) and display names
- **Media URLs** — links to images/videos hosted on Twitter CDN (`pbs.twimg.com`)
- **Links** — URLs embedded in tweets (expanded from `t.co` short links)
- **Engagement metadata** — retweet/quote attribution
- **LLM-generated analysis** — relevance scores, summaries, tickers, narratives,
  image descriptions, article summaries and action items

## Data Storage

| Store | Location | Contents |
|-------|----------|----------|
| SQLite database | `~/.local/share/twag/tweets.db` (configurable) | All tweet data, accounts, narratives, reactions, prompts, fetch logs |
| Digest files | `~/.local/share/twag/digests/` | Markdown digest exports |
| Config | `~/.config/twag/` | Following list, settings |
| Credentials | `~/.env` or environment variables | API keys and auth tokens |

### Database Tables

| Table | Privacy-relevant data |
|-------|----------------------|
| `tweets` | `author_handle`, `author_name`, `content`, `original_content`, `article_text`, `summary`, `links_json`, `original_author_handle`, `original_author_name`, `retweeted_by_handle`, `retweeted_by_name`, `analysis_json` |
| `accounts` | `handle`, `display_name`, `tier`, `weight`, `muted`, `tweets_seen`, `tweets_kept`, `avg_relevance_score` |
| `narratives` | `name`, `sentiment`, `related_tickers` |
| `tweet_narratives` | Junction table (tweet ↔ narrative) |
| `fetch_log` | `endpoint`, `query_params` |
| `reactions` | `reaction_type`, `reason`, `target` (may contain author handles) |
| `prompts` | `name`, `template`, `updated_by` |
| `prompt_history` | `prompt_name`, `template`, `version` |
| `context_commands` | `name`, `command_template`, `description` |
| `tweets_fts` | FTS5 index over `content`, `summary`, `author_handle`, `tickers` |

## External Services

### Twitter/X (via bird CLI)

- **What is sent:** authentication tokens (`AUTH_TOKEN`, `CT0`) as CLI flags
- **What is received:** tweet JSON payloads (content, authors, media, links)
- **Note:** auth tokens are visible in the process list while `bird` runs

### LLM APIs (Gemini / Anthropic)

- **Gemini (Google):** tweet text, author handles, prompts, and raw image bytes
  are sent to the Gemini API for scoring and vision analysis
- **Anthropic:** tweet text, author handles, prompts, and image URLs are sent to
  the Anthropic API; Anthropic fetches images server-side from the provided URL

Data sent to LLMs includes: full tweet text, author handles, quoted tweet text,
article summaries, image descriptions, link summaries, and LLM prompt templates.

### Telegram

- **What is sent:** author handle, tweet content preview (up to 150 chars),
  LLM-generated summary, tickers, and tweet URL
- **Sent via:** `POST` to `https://api.telegram.org/bot{token}/sendMessage`

### Link Expansion Destinations

- **What is sent:** HTTP HEAD/GET requests to `t.co` short URLs, which redirect
  to the final destination URL
- **User-Agent:** `twag/1.0 (+https://github.com/clifton/twag)`
- **Scope:** only `t.co` domain URLs are expanded; max 512 per process lifetime

### Image Fetching (for Gemini vision)

- **What is fetched:** raw image bytes from tweet media URLs
  (typically `pbs.twimg.com`)
- **Via:** `httpx.get()` with 30s timeout

## Credential Handling

| Credential | Source | Usage |
|------------|--------|-------|
| `AUTH_TOKEN` | `~/.env` or env var | Twitter session token, passed as bird CLI flag |
| `CT0` | `~/.env` or env var | Twitter CSRF token, passed as bird CLI flag |
| `GEMINI_API_KEY` | `~/.env` or env var | Google Gemini API authentication |
| `ANTHROPIC_API_KEY` | `~/.env` or env var | Anthropic API authentication |
| `TELEGRAM_BOT_TOKEN` | env var only | Telegram bot API authentication |
| `TELEGRAM_CHAT_ID` | env var or config | Telegram destination chat |

Credentials are loaded by `twag/auth.py` from environment variables or `~/.env`.
The full process environment is passed to the `bird` subprocess.

## Web API Exposure

The web interface binds to **localhost only** (`127.0.0.1`). CORS is restricted
to `localhost` and `127.0.0.1` origins.

- **No authentication** is required to access the web API
- **No cookies or sessions** are used
- **No analytics or tracking** is present

### Endpoints

| Method | Path | Data exposed |
|--------|------|--------------|
| GET | `/api/tweets` | Paginated tweet feed with content, summaries, media, links, author data |
| GET | `/api/tweets/{tweet_id}` | Single tweet with all stored fields |
| GET | `/api/categories` | Category counts |
| GET | `/api/tickers` | Ticker mention counts |
| POST | `/api/react` | Store reaction (can trigger account muting) |
| GET | `/api/reactions/{tweet_id}` | Reactions for a tweet |
| DELETE | `/api/reactions/{reaction_id}` | Delete a reaction |
| GET | `/api/reactions/summary` | Reaction type counts |
| GET | `/api/reactions/export` | Reactions with tweet data for LLM prompt tuning |
| GET | `/api/prompts` | LLM prompt templates |
| GET | `/api/prompts/{name}` | Single prompt |
| PUT | `/api/prompts/{name}` | Update prompt |
| GET | `/api/prompts/{name}/history` | Prompt version history |
| POST | `/api/prompts/{name}/rollback` | Rollback prompt |
| POST | `/api/prompts/tune` | Send reactions + tweet content to LLM |
| POST | `/api/prompts/{name}/apply-suggestion` | Apply LLM suggestion |
| GET | `/api/context-commands` | Shell command templates |
| POST | `/api/context-commands` | Create command template |
| GET | `/api/context-commands/{name}` | Get command |
| PUT | `/api/context-commands/{name}` | Update command |
| DELETE | `/api/context-commands/{name}` | Delete command |
| POST | `/api/context-commands/{name}/toggle` | Enable/disable command |
| POST | `/api/context-commands/{name}/test` | Execute shell command with tweet variable substitution |
| POST | `/api/analyze/{tweet_id}` | Run shell commands + LLM analysis on tweet |
| GET | `/{full_path:path}` | SPA frontend catch-all |

## Data Retention

- The `twag prune` command removes tweets older than a configurable threshold
- No automatic data expiration — pruning is user-initiated
- Digest files persist until manually deleted

## Logging

- Python logging may include tweet IDs, bird CLI command names, and stderr output
- **No tweet content, author handles, or URLs are written to log output**
- Rich console output to terminal (stdout) includes tweet content and author
  handles during interactive CLI use
