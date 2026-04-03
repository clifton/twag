"""Tests for the in-memory metrics module."""

from __future__ import annotations

import threading

from twag import metrics


def setup_function():
    metrics.reset()


def test_counter_default_increment():
    metrics.counter("requests")
    data = metrics.get_all_metrics()
    assert data["counters"]["requests"] == 1.0


def test_counter_custom_increment():
    metrics.counter("bytes", value=512)
    metrics.counter("bytes", value=256)
    data = metrics.get_all_metrics()
    assert data["counters"]["bytes"] == 768.0


def test_counter_with_labels():
    metrics.counter("llm.calls", labels={"provider": "gemini"})
    metrics.counter("llm.calls", labels={"provider": "anthropic"})
    metrics.counter("llm.calls", labels={"provider": "gemini"})
    data = metrics.get_all_metrics()
    assert data["counters"]["llm.calls{provider=gemini}"] == 2.0
    assert data["counters"]["llm.calls{provider=anthropic}"] == 1.0


def test_histogram_running_summary():
    metrics.histogram("latency", 1.0)
    metrics.histogram("latency", 3.0)
    metrics.histogram("latency", 2.0)
    snap = metrics.get_all_metrics()["histograms"]["latency"]
    assert snap["count"] == 3
    assert snap["min"] == 1.0
    assert snap["max"] == 3.0
    assert snap["avg"] == 2.0
    assert snap["total"] == 6.0


def test_histogram_with_labels():
    metrics.histogram("dur", 0.5, labels={"route": "/api/a"})
    metrics.histogram("dur", 1.5, labels={"route": "/api/b"})
    data = metrics.get_all_metrics()["histograms"]
    assert "dur{route=/api/a}" in data
    assert "dur{route=/api/b}" in data


def test_timer_records_histogram():
    with metrics.timer("op_time"):
        pass  # near-zero duration
    snap = metrics.get_all_metrics()["histograms"]["op_time"]
    assert snap["count"] == 1
    assert snap["min"] >= 0


def test_timer_records_on_exception():
    try:
        with metrics.timer("fail_time"):
            raise ValueError("boom")
    except ValueError:
        pass
    snap = metrics.get_all_metrics()["histograms"]["fail_time"]
    assert snap["count"] == 1


def test_reset_clears_all():
    metrics.counter("a")
    metrics.histogram("b", 1.0)
    metrics.reset()
    data = metrics.get_all_metrics()
    assert data["counters"] == {}
    assert data["histograms"] == {}


def test_dump_json(tmp_path):
    metrics.counter("x", value=5)
    path = str(tmp_path / "metrics.json")
    text = metrics.dump_json(path)
    assert '"x": 5.0' in text
    with open(path) as f:
        assert f.read() == text


def test_thread_safety():
    """Concurrent counter increments should not lose updates."""
    barrier = threading.Barrier(4)

    def bump():
        barrier.wait()
        for _ in range(1000):
            metrics.counter("concurrent")

    threads = [threading.Thread(target=bump) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert metrics.get_all_metrics()["counters"]["concurrent"] == 4000.0


def test_histogram_no_unbounded_memory():
    """Histogram should use running summary, not store individual observations."""
    for i in range(10_000):
        metrics.histogram("big", float(i))
    snap = metrics.get_all_metrics()["histograms"]["big"]
    assert snap["count"] == 10_000
    # Verify the internal object doesn't have a growing list
    key = "big"
    h = metrics._histograms[key]
    assert not hasattr(h, "values") or not isinstance(getattr(h, "values", None), list)


def test_label_key_deterministic():
    """Labels with same keys but different insertion order produce the same key."""
    k1 = metrics._label_key("m", {"a": "1", "b": "2"})
    k2 = metrics._label_key("m", {"b": "2", "a": "1"})
    assert k1 == k2
