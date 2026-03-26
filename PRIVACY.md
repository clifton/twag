# Privacy Policy

Last updated: 2026-03-25

This document describes the data twag collects, stores, and transmits. It is
validated automatically by `scripts/check_privacy.py`.

---

## 1. Data Collection

### Twitter/X Data

twag fetches tweets through the `bird` CLI binary. Data collected per tweet:

- Tweet ID, content text, creation timestamp
- Author handle and display name
- Media attachments (images, videos) and URLs
- Retweet and quote-tweet metadata
- Bookmark status
- Article content for X Articles (title, body, summary, visuals)

### User-Generated Data

- **Reactions** — user feedback on tweets (boost, upvote, downvote, mute author/topic)
- **Prompt templates** — user-edited LLM scoring prompts with version history
- **Context commands** — user-defined shell command templates for tweet enrichment
- **Account configuration** — tier, weight, category, mute/boost settings for tracked handles

---

## 2. Data Storage

All data is stored locally in a SQLite database. No cloud database is used.

### Database Tables

| Table | Contents |
|-------|----------|
| `tweets` | Tweet content, metadata, scores, summaries, media, links, article data |
| `accounts` | Tracked Twitter handles with tier/weight/category settings |
| `narratives` | Emerging market themes with sentiment and tickers |
| `tweet_narratives` | Junction table linking tweets to narratives |
| `fetch_log` | Fetch operation history (endpoint, counts, timing) |
| `reactions` | User feedback on tweets |
| `prompts` | Editable LLM prompt templates |
| `prompt_history` | Prompt version history for rollback |
| `context_commands` | User-defined shell command templates |
| `tweets_fts` | Full-text search index (content, summary, author, tickers) |

### File Locations

- Database: `~/.local/share/twag/twag.db` (or `$TWAG_DATA_DIR/twag.db`)
- Config: `~/.config/twag/config.yaml` (or `$XDG_CONFIG_HOME/twag/config.yaml`)
- Following list: `~/.config/twag/following.txt`

---

## 3. External Services

### Twitter/X (via bird CLI)

- **Data sent:** Authentication tokens (`AUTH_TOKEN`, `CT0`), search queries
- **Data received:** Tweet content, author info, media URLs
- **Protocol:** bird CLI handles all network communication

### Anthropic API

- **Data sent:** Tweet content, author handle, scoring context, image data (via vision)
- **Data received:** Relevance scores, summaries, analysis
- **Credential:** `ANTHROPIC_API_KEY`

### Google Gemini API

- **Data sent:** Tweet content, author handle, scoring context, image data (via vision)
- **Data received:** Relevance scores, summaries, analysis
- **Credential:** `GEMINI_API_KEY`

### Telegram API

- **Data sent:** Alert messages containing author handle, 150-char content preview, summary, tickers, tweet URL
- **Data received:** Delivery confirmation
- **Credentials:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

### URL Expansion

- **Data sent:** HTTP HEAD/GET requests to `t.co` and destination URLs
- **User-Agent:** `twag/1.0 (+https://github.com/clifton/twag)`
- **Purpose:** Resolve short URLs to final destinations

---

## 4. Credentials

All credentials are loaded from environment variables or a `~/.env` file.

| Variable | Purpose |
|----------|---------|
| `AUTH_TOKEN` | Twitter/X session authentication |
| `CT0` | Twitter/X CSRF token |
| `ANTHROPIC_API_KEY` | Anthropic API access |
| `GEMINI_API_KEY` | Google Gemini API access |
| `TELEGRAM_BOT_TOKEN` | Telegram bot authentication |
| `TELEGRAM_CHAT_ID` | Telegram notification target |

---

## 5. Web API Endpoints

The local web server exposes these endpoints:

| Method | Path | Data Exposed |
|--------|------|-------------|
| GET | `/tweets` | Paginated tweet feed with scores and metadata |
| GET | `/tweets/{tweet_id}` | Single tweet with full enrichment |
| GET | `/categories` | Category names and tweet counts |
| GET | `/tickers` | Ticker symbols and counts |
| POST | `/react` | Creates a reaction record |
| GET | `/reactions/{tweet_id}` | Reactions for a specific tweet |
| DELETE | `/reactions/{reaction_id}` | Removes a reaction |
| GET | `/reactions/summary` | Reaction counts by type |
| GET | `/reactions/export` | Full reaction export with tweet data |
| GET | `/prompts` | List prompt templates |
| GET | `/prompts/{name}` | Single prompt template |
| PUT | `/prompts/{name}` | Update prompt template |
| GET | `/prompts/{name}/history` | Prompt version history |
| POST | `/prompts/{name}/rollback` | Rollback prompt to prior version |
| POST | `/prompts/tune` | LLM-assisted prompt tuning |
| POST | `/prompts/{name}/apply-suggestion` | Apply LLM suggestion |
| GET | `/context-commands` | List context commands |
| POST | `/context-commands` | Create context command |
| GET | `/context-commands/{name}` | Single context command |
| PUT | `/context-commands/{name}` | Update context command |
| DELETE | `/context-commands/{name}` | Delete context command |
| POST | `/context-commands/{name}/toggle` | Enable/disable command |
| POST | `/context-commands/{name}/test` | Test command against tweet |
| POST | `/analyze/{tweet_id}` | Deep-analyze tweet with context commands |

All endpoints serve locally only. No authentication is required by default.

---

## 6. Logging

twag does **not** log personal data (tweet content, author handles, usernames).

Log output is limited to:
- Operational metrics (byte counts, tweet counts, timing)
- Tweet IDs (opaque numeric identifiers)
- Error messages from the bird CLI (generic errors, not content)
- Failure reasons for skipped tweets (e.g., "tweet unavailable")

**Data transmitted to external services but not logged:**
- Tweet content and author handles are sent to Anthropic/Gemini APIs in scoring prompts
- Author handles and content previews are sent to Telegram in alert messages

---

## 7. Data Retention

- **Tweets:** Retained indefinitely unless explicitly pruned via `twag prune`
- **Fetch log:** Retained indefinitely
- **Reactions:** Retained indefinitely unless deleted via API
- **Prompts:** All versions retained for rollback
- **Database exports:** Created on-demand via `twag export` or `twag db dump`

No automatic data deletion or expiration is configured.
