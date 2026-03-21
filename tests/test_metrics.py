"""Tests for the metrics module."""

from twag.metrics import (
    BIRD_CALL_DURATION,
    BIRD_OUTCOMES,
    DB_LOCK_RETRIES,
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS,
    LLM_CALL_DURATION,
    LLM_ERRORS,
    LLM_RETRIES,
    NOTIFICATION_DURATION,
    NOTIFICATION_OUTCOMES,
    REGISTRY,
    TRIAGE_BATCH_DURATION,
    TRIAGE_ERRORS,
    TRIAGE_TIER_COUNTS,
    TWEET_INSERTS,
)


def test_registry_contains_all_metrics():
    """All defined metrics are registered in the shared registry."""
    from prometheus_client import generate_latest

    output = generate_latest(REGISTRY).decode()
    expected = [
        "twag_llm_call_duration_seconds",
        "twag_llm_errors",
        "twag_llm_retries",
        "twag_bird_call_duration_seconds",
        "twag_bird_call_outcomes",
        "twag_triage_batch_duration_seconds",
        "twag_triage_tier",
        "twag_triage_errors",
        "twag_http_request_duration_seconds",
        "twag_http_requests",
        "twag_notification_outcomes",
        "twag_notification_duration_seconds",
        "twag_db_lock_retries",
        "twag_tweet_inserts",
    ]
    for name in expected:
        assert name in output, f"Metric {name} not found in /metrics output"


def test_counter_increment():
    """Counters can be incremented and reflect the change."""
    before = LLM_RETRIES._value.get()
    LLM_RETRIES.inc()
    assert LLM_RETRIES._value.get() == before + 1


def test_labeled_counter():
    """Labeled counters produce correct child metrics."""
    TWEET_INSERTS.labels(outcome="new").inc()
    TWEET_INSERTS.labels(outcome="duplicate").inc(3)
    # Just verify no exceptions — label initialization works


def test_histogram_observe():
    """Histograms accept observations without error."""
    LLM_CALL_DURATION.labels(provider="gemini", operation="text").observe(0.5)
    BIRD_CALL_DURATION.labels(command="home").observe(1.2)
    HTTP_REQUEST_DURATION.labels(method="GET", route="/api/tweets", status="200").observe(0.05)
    NOTIFICATION_DURATION.observe(0.3)
    TRIAGE_BATCH_DURATION.observe(5.0)


def test_all_metric_objects_are_importable():
    """Smoke-test that all public metric objects are the expected types."""
    from prometheus_client import Counter, Histogram

    for obj in [
        LLM_CALL_DURATION,
        BIRD_CALL_DURATION,
        TRIAGE_BATCH_DURATION,
        HTTP_REQUEST_DURATION,
        NOTIFICATION_DURATION,
    ]:
        assert isinstance(obj, Histogram)
    for obj in [
        LLM_ERRORS,
        LLM_RETRIES,
        BIRD_OUTCOMES,
        TRIAGE_TIER_COUNTS,
        TRIAGE_ERRORS,
        HTTP_REQUESTS,
        NOTIFICATION_OUTCOMES,
        DB_LOCK_RETRIES,
        TWEET_INSERTS,
    ]:
        assert isinstance(obj, Counter)
