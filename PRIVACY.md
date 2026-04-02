# Privacy Policy

Last updated: 2026-04-01

twag is a **single-user, locally-hosted** Twitter/X market signal aggregator.
It is designed to run on your own machine and does not collect or share data
with anyone other than the external services listed below.

---

## 1. Data Collected

twag stores **publicly available Twitter/X data** in a local SQLite database:

| Data type | Where stored | Source |
|-----------|-------------|--------|
| Tweet text and metadata | `tweets` table | Twitter/X via `bird` CLI |
| Author handles and display names | `tweets`, `accounts` tables | Twitter/X via `bird` CLI |
| Retweet/quote attribution | `tweets` table | Twitter/X via `bird` CLI |
| Media URLs and analysis | `tweets` table | Twitter/X via `bird` CLI |
| Expanded link URLs | `tweets.links_json` | URL expansion during processing |
| LLM scoring results | `tweets` table | Generated locally via LLM APIs |
| User reactions and feedback | `reactions` table | User input via web UI or CLI |
| Fetch history | `fetch_log` table | Generated locally |
| Narrative tracking | `narratives`, `tweet_narratives` tables | Generated locally via LLM APIs |
| Editable prompts | `prompts`, `prompt_history` tables | User input |
| Context commands | `context_commands` table | User input |

All data is stored in a local SQLite file. No remote database is used.

---

## 2. Credentials

twag requires the following credentials, stored as environment variables or in
a `~/.env` file:

| Credential | Purpose |
|------------|---------|
| `AUTH_TOKEN` | Twitter/X session authentication (passed to `bird` CLI) |
| `CT0` | Twitter/X CSRF token (passed to `bird` CLI) |
| `GEMINI_API_KEY` | Google Gemini LLM API access |
| `ANTHROPIC_API_KEY` | Anthropic Claude LLM API access |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API for push notifications |
| `TELEGRAM_CHAT_ID` | Telegram chat target for push notifications |

Credentials are **never logged** by twag. They are read from environment
variables or `~/.env` and passed only to their respective services.

---

## 3. External Services

twag contacts the following external services at runtime:

| Service | When | Data sent | Library |
|---------|------|-----------|---------|
| **Twitter/X** (via `bird` CLI) | `twag fetch` | Auth credentials via subprocess | `subprocess` |
| **Google Gemini API** | `twag process` | Tweet text, media image URLs | `google-genai` SDK |
| **Anthropic Claude API** | `twag process` | Tweet text | `anthropic` SDK |
| **Telegram Bot API** | `twag digest` (when notifications enabled) | Tweet summaries, author handles, links | `httpx` |
| **t.co** (Twitter short URLs) | `twag process` (link expansion) | HTTP HEAD/GET requests with User-Agent `twag/1.0` | `urllib.request` |
| **Tweet media hosts** (`pbs.twimg.com`) | `twag process` (image analysis) | HTTP GET to fetch images for LLM vision | `httpx` |
| **Google Fonts CDN** (`fonts.googleapis.com`, `fonts.gstatic.com`) | Web UI page load | Browser IP address (standard font request) | Browser `<link>` tag |

No analytics, tracking pixels, or third-party JavaScript is loaded.

---

## 4. Web Endpoints

The web UI exposes a local FastAPI server with these API routes:

### Tweets
- `GET /api/tweets` -- List tweets with filters
- `GET /api/tweets/{tweet_id}` -- Single tweet detail
- `GET /api/categories` -- List categories
- `GET /api/tickers` -- List tickers

### Reactions
- `POST /api/react` -- Add a reaction
- `GET /api/reactions/{tweet_id}` -- Get reactions for a tweet
- `DELETE /api/reactions/{reaction_id}` -- Delete a reaction
- `GET /api/reactions/summary` -- Reaction summary
- `GET /api/reactions/export` -- Export reactions

### Prompts
- `GET /api/prompts` -- List prompts
- `GET /api/prompts/{name}` -- Get a prompt
- `PUT /api/prompts/{name}` -- Update a prompt
- `GET /api/prompts/{name}/history` -- Prompt history
- `POST /api/prompts/{name}/rollback` -- Rollback a prompt
- `POST /api/prompts/tune` -- Tune prompts
- `POST /api/prompts/{name}/apply-suggestion` -- Apply a suggestion

### Context Commands
- `GET /api/context-commands` -- List context commands
- `POST /api/context-commands` -- Create a context command
- `GET /api/context-commands/{name}` -- Get a context command
- `PUT /api/context-commands/{name}` -- Update a context command
- `DELETE /api/context-commands/{name}` -- Delete a context command
- `POST /api/context-commands/{name}/toggle` -- Toggle a context command
- `POST /api/context-commands/{name}/test` -- Test a context command
- `POST /api/analyze/{tweet_id}` -- Re-analyze a tweet

The web server is intended for **local use only** and does not require
authentication by default.

---

## 5. Logging

twag logs operational messages (fetch counts, processing progress, errors) to
stderr. **No personal data** (tweet content, author handles, or credentials) is
intentionally logged by twag code. The `bird` CLI subprocess stderr output is
forwarded at WARNING level; its content depends on the external `bird` binary.

---

## 6. Data Retention

- Tweets are retained indefinitely unless pruned via `twag prune`
- Fetch logs are retained indefinitely unless the database is manually cleaned
- No automatic data expiration or remote backup exists
- All data can be deleted by removing the local SQLite database file
