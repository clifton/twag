# CLI reference

Every twag command and subcommand, grouped by lifecycle. Source of truth is
[`twag/cli/`](../twag/cli/) — if a command's behavior changes, both this
reference and [`README.md`](../README.md) should be updated.

The top-level `twag` group exposes `--version` and standard `--help`.
Subcommands reuse the group's database and config.

## Setup

### `twag init`

Initialize twag data directories and configuration.

| Option | Default | Purpose |
|--------|---------|---------|
| `--force` | off | Overwrite existing config file |

### `twag doctor`

Check dependencies and environment (bird CLI, API keys, database).

## Pipeline

### `twag fetch [STATUS_ID_OR_URL]`

Fetch tweets from Twitter/X. Without an argument, fetches the home timeline
plus tier-1 accounts and bookmarks (each can be disabled). With a status ID
or URL, fetches just that tweet.

| Option | Default | Purpose |
|--------|---------|---------|
| `--source` | `home` | One of `home`, `user`, `search` |
| `--handle` / `-u` | — | Required when `--source user` |
| `--query` / `-q` | — | Required when `--source search` |
| `--count` / `-n` | 200 | Number of tweets to fetch |
| `--tier1` / `--no-tier1` | on | Also fetch tier-1 accounts after home fetch |
| `--bookmarks` / `--no-bookmarks` | on | Also fetch bookmarks after home fetch |
| `--delay` | config `fetch.tier1_delay` (3s) | Delay between tier-1 fetches |
| `--stagger` | config `fetch.tier1_stagger` | Limit tier-1 to N least-recently-fetched accounts |

### `twag process [STATUS_ID_OR_URL]`

Run unscored tweets through the LLM triage pipeline. With a status ID or
URL, processes just that tweet.

| Option | Default | Purpose |
|--------|---------|---------|
| `--limit` / `-n` | 250 | Max tweets per run |
| `--dry-run` | off | Preview only |
| `--model` / `-m` | config | Override the triage LLM model |
| `--notify` / `--no-notify` | off | Send Telegram alerts for high-signal tweets |
| `--reprocess-quotes` / `--no-reprocess-quotes` | on | Reprocess today's quote/reply dependency tweets after main pass |
| `--reprocess-min-score` | config `scoring.min_score_for_reprocess` (3) | Minimum score to include in dependency reprocessing |

### `twag analyze STATUS_ID_OR_URL`

Fetch, process, and print a structured analysis for one status.

| Option | Default | Purpose |
|--------|---------|---------|
| `--model` / `-m` | config | Override the triage LLM model |
| `--reprocess` / `--no-reprocess` | off | Re-run processing even if already processed |

### `twag digest`

Generate the daily digest as markdown.

| Option | Default | Purpose |
|--------|---------|---------|
| `--date` / `-d` | today | Date to render (YYYY-MM-DD) |
| `--stdout` | off | Print to stdout instead of writing to file |
| `--min-score` | config | Minimum relevance score for inclusion |

## Accounts

### `twag accounts list`

| Option | Default | Purpose |
|--------|---------|---------|
| `--tier` / `-t` | — | Filter by tier number |
| `--muted` | off | Include muted accounts |

### `twag accounts add HANDLE`

| Option | Default | Purpose |
|--------|---------|---------|
| `--tier` / `-t` | 2 | Account tier (1 = core, 2 = followed) |
| `--category` / `-c` | — | Account category label |

### `twag accounts promote HANDLE`

Promote an account to tier 1.

### `twag accounts demote HANDLE`

| Option | Default | Purpose |
|--------|---------|---------|
| `--tier` / `-t` | 2 | Target tier to demote to |

### `twag accounts mute HANDLE`

Mute an account so it is excluded from results.

### `twag accounts boost HANDLE`

| Option | Default | Purpose |
|--------|---------|---------|
| `--amount` | 5.0 | Amount added to the account's weight |

### `twag accounts decay`

Apply daily decay to all account weights.

| Option | Default | Purpose |
|--------|---------|---------|
| `--rate` | 0.05 | Decay rate (0–1) |

### `twag accounts import`

Import accounts from `following.txt`.

| Option | Default | Purpose |
|--------|---------|---------|
| `--tier` / `-t` | 2 | Default tier for imported accounts |

## Query

### `twag search [QUERY]`

FTS5 full-text search. Omit the query to browse without searching.

| Option | Default | Purpose |
|--------|---------|---------|
| `--category` / `-c` | — | Filter by category |
| `--author` / `-a` | — | Filter by author handle |
| `--min-score` / `-s` | — | Minimum relevance score |
| `--tier` / `-t` | — | Filter by signal tier |
| `--ticker` / `-T` | — | Filter by ticker symbol |
| `--bookmarks` / `-b` | off | Only bookmarked tweets |
| `--since` | — | Start time (`YYYY-MM-DD` or relative `1d`, `7d`, …) |
| `--until` | — | End time (`YYYY-MM-DD`) |
| `--today` | off | Since previous market close (4 pm ET) |
| `--time` | — | Time-range shorthand (`today`, `7d`, …) |
| `--limit` / `-n` | 20 | Max results |
| `--order` / `-o` | `rank` (with query) / `score` (without) | Sort order; `rank` uses BM25 and requires a query |
| `--format` / `-f` | `brief` | One of `brief`, `full`, `json` |

Query syntax: `inflation fed` (AND-of-terms), `"rate hike"` (phrase),
`fed AND powell`, `fed NOT fomc`, `infla*` (prefix).

### `twag narratives list`

List active narratives with mention counts.

## Maintenance

### `twag stats`

Show processing statistics.

| Option | Default | Purpose |
|--------|---------|---------|
| `--date` / `-d` | — | Date to show stats for |
| `--today` | off | Use the current date |

### `twag prune`

Delete old tweets.

| Option | Default | Purpose |
|--------|---------|---------|
| `--days` | 14 | Delete tweets older than N days |
| `--dry-run` | off | Preview without deleting |

### `twag export`

Export recent data.

| Option | Default | Purpose |
|--------|---------|---------|
| `--format` | `json` | Output format |
| `--days` | 7 | Export tweets from the last N days |

## Config

### `twag config show` / `twag config path`

Print the current config or its file path.

### `twag config set KEY VALUE`

Set a configuration value via dot-separated key (e.g.
`twag config set llm.triage_model gemini-2.0-flash`). Values are parsed as
JSON when valid, otherwise stored as strings.

## Database

### `twag db path` / `twag db shell` / `twag db init` / `twag db rebuild-fts`

Show the DB path; open an interactive `sqlite3` shell; (re)initialize the
schema; or rebuild the FTS5 index.

### `twag db dump [OUTPUT]`

FTS5-safe SQL dump.

| Option | Default | Purpose |
|--------|---------|---------|
| `OUTPUT` | `twag-YYYYMMDD-HHMMSS.sql` | Output file path |
| `--stdout` | off | Write to stdout instead of a file |

### `twag db restore INPUT_FILE`

Restore from a `.sql` or `.sql.gz` dump.

| Option | Default | Purpose |
|--------|---------|---------|
| `--force` | off | Overwrite existing database without prompting |

## Web

### `twag web`

Start the FastAPI server.

| Option | Default | Purpose |
|--------|---------|---------|
| `--host` / `-h` | `0.0.0.0` | Bind address |
| `--port` / `-p` | 5173 | Port |
| `--reload` / `--no-reload` | on | Auto-reload on code changes |
| `--dev` | off | Dev mode: also start Vite (port 8080) with HMR |

The web UI has no authentication. Bind to localhost or a trusted network
only.

## Metrics

### `twag metrics`

Show metrics instrumentation coverage summary (which subsystems have
emitted at least one metric this process). See [metrics.md](./metrics.md)
for the full list of emitted metrics.
