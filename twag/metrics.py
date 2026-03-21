"""Prometheus metrics for twag observability."""

from prometheus_client import CollectorRegistry, Counter, Histogram

# Shared registry — avoids polluting the global default registry in tests.
REGISTRY = CollectorRegistry()

# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------
LLM_CALL_DURATION = Histogram(
    "twag_llm_call_duration_seconds",
    "LLM call latency",
    ["provider", "operation"],
    registry=REGISTRY,
)
LLM_ERRORS = Counter(
    "twag_llm_errors_total",
    "LLM call errors",
    ["provider", "operation"],
    registry=REGISTRY,
)
LLM_RETRIES = Counter(
    "twag_llm_retries_total",
    "LLM retry attempts",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Bird CLI
# ---------------------------------------------------------------------------
BIRD_CALL_DURATION = Histogram(
    "twag_bird_call_duration_seconds",
    "bird CLI call latency",
    ["command"],
    registry=REGISTRY,
)
BIRD_OUTCOMES = Counter(
    "twag_bird_call_outcomes_total",
    "bird CLI call outcomes",
    ["command", "outcome"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Tweet triage / processing
# ---------------------------------------------------------------------------
TRIAGE_BATCH_DURATION = Histogram(
    "twag_triage_batch_duration_seconds",
    "Duration of a triage batch",
    registry=REGISTRY,
)
TRIAGE_TIER_COUNTS = Counter(
    "twag_triage_tier_total",
    "Tweets triaged per signal tier",
    ["tier"],
    registry=REGISTRY,
)
TRIAGE_ERRORS = Counter(
    "twag_triage_errors_total",
    "Triage processing errors",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# HTTP requests (FastAPI middleware)
# ---------------------------------------------------------------------------
HTTP_REQUEST_DURATION = Histogram(
    "twag_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route", "status"],
    registry=REGISTRY,
)
HTTP_REQUESTS = Counter(
    "twag_http_requests_total",
    "HTTP requests served",
    ["method", "route", "status"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Telegram notifications
# ---------------------------------------------------------------------------
NOTIFICATION_OUTCOMES = Counter(
    "twag_notification_outcomes_total",
    "Telegram notification outcomes",
    ["outcome"],
    registry=REGISTRY,
)
NOTIFICATION_DURATION = Histogram(
    "twag_notification_duration_seconds",
    "Telegram notification delivery latency",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# DB lock retries
# ---------------------------------------------------------------------------
DB_LOCK_RETRIES = Counter(
    "twag_db_lock_retries_total",
    "SQLite lock retry attempts",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Tweet inserts
# ---------------------------------------------------------------------------
TWEET_INSERTS = Counter(
    "twag_tweet_inserts_total",
    "Tweet insert outcomes",
    ["outcome"],
    registry=REGISTRY,
)
