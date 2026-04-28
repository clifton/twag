# Database schema

twag stores everything in a single SQLite database (default
`~/.local/share/twag/twag.db`). The schema is defined in
[`twag/db/schema.py`](../twag/db/schema.py) and split between `SCHEMA`
(core tables) and `FTS_SCHEMA` (FTS5 virtual table + sync triggers).

## Tables

### `tweets`

Core tweet storage with deduplication. Primary key is the Twitter status
ID.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | TEXT PK | Twitter status ID |
| `author_handle` | TEXT NOT NULL | Author handle (lowercase) |
| `author_name` | TEXT | Display name |
| `content` | TEXT NOT NULL | Tweet body |
| `created_at` | TIMESTAMP | Tweet creation time (from upstream) |
| `first_seen_at` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | When twag first saw it |
| `source` | TEXT | Where it came from (`home`, `user`, `search`, `bookmark`, `tier1`, `dependency`, …) |
| `processed_at` | TIMESTAMP | Set when triage completes |
| `relevance_score` | REAL | Triage score 0–10 |
| `category` | TEXT | JSON list of categories |
| `summary` | TEXT | Triage summary |
| `content_summary` | TEXT | Summarized body for long tweets |
| `signal_tier` | TEXT | `high_signal`, `market_relevant`, `news`, `noise` |
| `tickers` | TEXT | JSON list of refined tickers |
| `analysis_json` | TEXT | Enrichment payload (insight, implications, narratives) |
| `has_quote` | INTEGER (bool) | Tweet quotes another |
| `quote_tweet_id` | TEXT FK→tweets.id | Quoted status ID |
| `in_reply_to_tweet_id` | TEXT | Status this is replying to |
| `conversation_id` | TEXT | Conversation/thread ID |
| `has_media` | INTEGER (bool) | Has any media attachment |
| `media_analysis` | TEXT | Vision-model output |
| `media_items` | TEXT | JSON of media items |
| `has_link` | INTEGER (bool) | Has any external link |
| `links_json` | TEXT | JSON of normalized/expanded links |
| `link_summary` | TEXT | Summary of linked content |
| `is_x_article` | INTEGER (bool) | X-native long-form article |
| `article_title` | TEXT | Article title |
| `article_preview` | TEXT | Article preview text |
| `article_text` | TEXT | Full article body |
| `article_summary_short` | TEXT | LLM short summary of the article |
| `article_primary_points_json` | TEXT | JSON list of primary points |
| `article_action_items_json` | TEXT | JSON list of action items |
| `article_top_visual_json` | TEXT | JSON for the selected top visual |
| `article_processed_at` | TIMESTAMP | When article processing finished |
| `links_expanded_at` | TIMESTAMP | When `t.co` expansion finished |
| `quote_reprocessed_at` | TIMESTAMP | When quote-aware reprocessing ran |
| `is_retweet` | INTEGER (bool) | Native retweet |
| `retweeted_by_handle` | TEXT | Handle that retweeted |
| `retweeted_by_name` | TEXT | Display name of retweeter |
| `original_tweet_id` | TEXT | ID of the original tweet |
| `original_author_handle` | TEXT | Original author handle |
| `original_author_name` | TEXT | Original author display name |
| `original_content` | TEXT | Original tweet content |
| `included_in_digest` | TEXT | Comma-separated digest dates this appeared in |
| `bookmarked` | INTEGER (bool) | User bookmarked the tweet |
| `bookmarked_at` | TIMESTAMP | When the bookmark was first observed |

Indexes:

- `idx_tweets_created` — `created_at DESC`
- `idx_tweets_score` — `relevance_score DESC`
- `idx_tweets_unprocessed` — partial: `processed_at IS NULL`
- `idx_tweets_processed_at_not_null` — partial: `processed_at IS NOT NULL`
- `idx_tweets_processed_score` — `(processed_at, relevance_score DESC, created_at DESC)`
- `idx_tweets_processed_created` — `(processed_at, created_at DESC)`
- `idx_tweets_author` — `author_handle`
- `idx_tweets_signal_tier` — `signal_tier`
- `idx_tweets_bookmarked` — partial: `bookmarked = 1`
- `idx_tweets_quote` — partial: `quote_tweet_id IS NOT NULL`

### `accounts`

Tracked authors with tier, weight, and rolling stats.

| Column | Type | Purpose |
|--------|------|---------|
| `handle` | TEXT PK | Account handle (lowercase) |
| `display_name` | TEXT | Display name |
| `tier` | INTEGER DEFAULT 2 | 1 = core, 2 = followed |
| `weight` | REAL DEFAULT 50.0 | Boost weight (subject to decay) |
| `category` | TEXT | Account label |
| `tweets_seen` | INTEGER | Total tweets observed |
| `tweets_kept` | INTEGER | Tweets that scored above noise |
| `avg_relevance_score` | REAL | Rolling average score |
| `last_high_signal_at` | TIMESTAMP | Last high-signal hit |
| `last_fetched_at` | TIMESTAMP | Last tier-1 fetch (drives rotation) |
| `added_at` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | When tracked |
| `auto_promoted` | INTEGER (bool) | Promoted by bookmark heuristic |
| `muted` | INTEGER (bool) | Hide from results |

Index: `idx_accounts_tier` on `(tier, weight DESC)`.

### `narratives` and `tweet_narratives`

Emerging-theme tracking.

`narratives`:

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `name` | TEXT NOT NULL | Narrative label |
| `first_seen_at` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | |
| `last_mentioned_at` | TIMESTAMP | |
| `mention_count` | INTEGER DEFAULT 1 | |
| `sentiment` | TEXT | Bullish/bearish/neutral |
| `related_tickers` | TEXT | JSON list |
| `active` | INTEGER DEFAULT 1 | |

`tweet_narratives` — junction (composite PK `tweet_id, narrative_id`).

### `fetch_log`

Per-fetch record for rate-limit tracking.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `endpoint` | TEXT NOT NULL | `home`, `user:<handle>`, `search`, `bookmarks`, … |
| `executed_at` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | |
| `tweets_fetched` | INTEGER | |
| `new_tweets` | INTEGER | |
| `query_params` | TEXT | JSON of parameters |

Index: `idx_fetch_log_endpoint` on `(endpoint, executed_at DESC)`.

### `reactions`

User feedback signals from the web UI.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `tweet_id` | TEXT NOT NULL FK→tweets.id | |
| `reaction_type` | TEXT NOT NULL | `>>`, `>`, `<`, `x_author`, `x_topic` |
| `reason` | TEXT | Optional free-text explanation |
| `target` | TEXT | Author handle (for `x_author`) or category (`x_topic`) |
| `created_at` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | |

Indexes: `idx_reactions_tweet` on `tweet_id`, `idx_reactions_type` on
`reaction_type`.

### `prompts` and `prompt_history`

Editable LLM prompts (extracted from `scorer/prompts.py`).

`prompts`:

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `name` | TEXT UNIQUE NOT NULL | e.g. `triage`, `batch_triage`, `enrichment` |
| `template` | TEXT NOT NULL | Prompt body |
| `version` | INTEGER DEFAULT 1 | |
| `updated_at` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | |
| `updated_by` | TEXT | `user` or `llm` |

`prompt_history` mirrors the schema and stores prior versions for rollback.
Index: `idx_prompt_history_name` on `(prompt_name, version DESC)`.

### `context_commands`

Allowlisted shell commands the web UI can run to enrich a tweet during
deep analysis.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `name` | TEXT UNIQUE NOT NULL | e.g. `market_snapshot` |
| `command_template` | TEXT NOT NULL | Shell template with `{var}` placeholders |
| `description` | TEXT | |
| `enabled` | INTEGER DEFAULT 1 | |
| `created_at` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | |

Allowed base commands and forbidden metacharacters are enforced at write
time by [`twag/web/routes/context.py`](../twag/web/routes/context.py); see
[web-api.md](./web-api.md) for the list.

### `alert_log`

Telegram alert history for rate limiting.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `tweet_id` | TEXT FK→tweets.id | Tweet that triggered the alert |
| `sent_at` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | |
| `chat_id` | TEXT | Telegram chat target |

Index: `idx_alert_log_sent` on `sent_at DESC`.

### `metrics`

Persisted snapshot of in-memory metrics (written via
`MetricsCollector.flush_to_db`). See [metrics.md](./metrics.md).

| Column | Type | Purpose |
|--------|------|---------|
| `name` | TEXT NOT NULL | Metric name (with optional `{labels}` suffix) |
| `type` | TEXT NOT NULL | `counter`, `gauge`, or `histogram` |
| `value` | REAL NOT NULL | Counter/gauge value, or histogram mean |
| `labels_json` | TEXT | JSON stats (count/min/max/p50/p99) for histograms |
| `recorded_at` | TEXT DEFAULT (strftime ISO 8601) | |

Index: `idx_metrics_name` on `(name, recorded_at DESC)`.

## Full-text search

`tweets_fts` is an FTS5 virtual table over
`(content, summary, author_handle, tickers)` with `content=tweets` and
`content_rowid=rowid`. Three triggers keep it in sync:

- `tweets_ai` — INSERT mirror.
- `tweets_ad` — DELETE mirror (uses FTS5 `'delete'` command).
- `tweets_au` — UPDATE: delete-old + insert-new.

`twag db rebuild-fts` rebuilds the index from scratch (e.g. after restoring
a dump that did not include the FTS contents).

## Maintenance

- `twag db init` — apply `SCHEMA` + `FTS_SCHEMA` (idempotent — uses
  `IF NOT EXISTS` everywhere).
- `twag db dump [OUTPUT] [--stdout]` — FTS5-safe SQL dump.
- `twag db restore INPUT_FILE [--force]` — restore from a `.sql` or
  `.sql.gz` dump.
- `twag db rebuild-fts` — rebuild only the FTS index.
- `twag prune --days N` — delete tweets older than N days.

The connection layer (`twag/db/connection.py`) initializes the database on
demand via `init_db(path)`.
