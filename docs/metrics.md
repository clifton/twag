# Metrics

twag has lightweight, dependency-free instrumentation in
[`twag/metrics.py`](../twag/metrics.py): counters, gauges, and histograms
held in memory and optionally flushed to the `metrics` SQLite table.

## API

Two equivalent surfaces:

- **Class-based:** `get_collector()` returns the singleton
  `MetricsCollector`. Methods: `inc(name, value=1.0)`, `set_gauge(name, value)`,
  `observe(name, value)`, `counter_value`, `gauge_value`,
  `histogram_stats`, `snapshot`, `instrumented_subsystems`,
  `flush_to_db(conn)`, `reset()`.
- **Module-level convenience:** `counter(name, *, value=1.0, labels=None)`,
  `histogram(name, value, *, labels=None)`, `timer(name, *, labels=None)`
  (context manager), `get_all_metrics()`, `dump_json(path=None)`,
  `reset()`.

Labels are encoded into the metric name as `name{k1=v1,k2=v2}` (sorted
keys). Histograms hold up to 1000 observations per metric (oldest 25%
rotated out when full).

`get_all_metrics()` returns:

```python
{
  "counters": {name: float, ...},
  "histograms": {name: {"count": int, "min": float, "max": float, "avg": float, "total": float}, ...},
}
```

The collector's `snapshot()` adds `uptime_seconds`, `gauges`, and
extra histogram percentiles (`p50`, `p99`).

## Persistence

`MetricsCollector.flush_to_db(conn)` writes the current snapshot into the
`metrics` table:

| Column | Source |
|--------|--------|
| `name` | metric name (with `{labels}` if any) |
| `type` | `counter`, `gauge`, or `histogram` |
| `value` | counter/gauge value, or histogram mean |
| `labels_json` | JSON of histogram stats (count/min/max/p50/p99) for histograms; `NULL` otherwise |
| `recorded_at` | ISO 8601 UTC timestamp |

`ensure_metrics_table(conn)` creates the table on demand (it is also part
of [`db/schema.py`](../twag/db/schema.py)).

## Subsystem coverage

`instrumented_subsystems()` reports which prefixes have at least one
metric:

| Subsystem | Prefix |
|-----------|--------|
| Scorer | `scorer.` |
| Pipeline | `pipeline.` |
| Fetcher | `fetcher.` |
| Web | `web.` |

`twag metrics` prints this coverage summary.

## Emitted metrics

### Web (`twag/web/app.py`)

| Metric | Type | Description |
|--------|------|-------------|
| `web.requests` | counter | HTTP requests handled |
| `web.request_latency_seconds` | histogram | Per-request latency |

### Fetcher (`twag/fetcher/bird_cli.py`)

| Metric | Type | Description |
|--------|------|-------------|
| `fetcher.calls` | counter | Bird subprocess invocations |
| `fetcher.errors` | counter | Subprocess failures and non-zero exits |
| `fetcher.retries` | counter | Retry attempts after a transient failure |
| `fetcher.latency_seconds` | histogram | Per-call wall time |

### Scorer (`twag/scorer/llm_client.py`)

| Metric | Type | Description |
|--------|------|-------------|
| `scorer.anthropic.calls` | counter | Anthropic API calls |
| `scorer.anthropic.errors` | counter | Anthropic API errors |
| `scorer.anthropic.latency_seconds` | histogram | Anthropic call latency |
| `scorer.anthropic.input_tokens` | counter | Input tokens consumed |
| `scorer.anthropic.output_tokens` | counter | Output tokens produced |
| `scorer.gemini.calls` | counter | Gemini API calls |
| `scorer.gemini.errors` | counter | Gemini API errors |
| `scorer.gemini.latency_seconds` | histogram | Gemini call latency |
| `scorer.retries` | counter | Retry attempts across providers |

### Pipeline (`twag/processor/`)

| Metric | Type | Description |
|--------|------|-------------|
| `pipeline.process_unprocessed.latency_seconds` | histogram | End-to-end `process_unprocessed` runtime |
| `pipeline.process_unprocessed.tweets` | counter | Tweets processed in the pass |
| `pipeline.triage.processed` | counter | Tweets that completed triage |
| `pipeline.triage.batch_errors` | counter | Triage batch failures |

## Inspecting metrics

- `twag metrics` — instrumentation coverage summary.
- `GET /api/metrics` — full snapshot including counters, gauges,
  histograms (with `p50`/`p99`), and subsystem coverage.
- `metrics.dump_json(path=None)` — JSON dump of the current snapshot,
  optionally written to a file.
- The `metrics` table holds historical flushes — query with
  `twag db shell`.
