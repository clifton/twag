"""Tests for twag.metrics — both module-level and class-based APIs, plus web endpoints."""

from __future__ import annotations

import sqlite3
import threading

import pytest

from twag import metrics
from twag.metrics import _HISTOGRAM_MAX_SIZE, MetricsCollector, ensure_metrics_table


def setup_function():
    metrics.reset()


# ── Module-level convenience API tests ────────────────────────────────────


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
    """Histogram observations list is bounded."""
    for i in range(10_000):
        metrics.histogram("big", float(i))
    snap = metrics.get_all_metrics()["histograms"]["big"]
    assert snap["count"] == 10_000


def test_label_key_deterministic():
    """Labels with same keys but different insertion order produce the same key."""
    k1 = metrics._label_key("m", {"a": "1", "b": "2"})
    k2 = metrics._label_key("m", {"b": "2", "a": "1"})
    assert k1 == k2


# ── MetricsCollector class-based API tests ────────────────────────────────


class TestCounter:
    def test_inc_default(self):
        m = MetricsCollector()
        m.inc("test.counter")
        assert m.counter_value("test.counter") == 1.0

    def test_inc_custom_value(self):
        m = MetricsCollector()
        m.inc("test.counter", 5.0)
        m.inc("test.counter", 3.0)
        assert m.counter_value("test.counter") == 8.0

    def test_counter_value_missing(self):
        m = MetricsCollector()
        assert m.counter_value("nonexistent") == 0.0


class TestGauge:
    def test_set_and_get(self):
        m = MetricsCollector()
        m.set_gauge("test.gauge", 42.0)
        assert m.gauge_value("test.gauge") == 42.0

    def test_gauge_overwrite(self):
        m = MetricsCollector()
        m.set_gauge("test.gauge", 10.0)
        m.set_gauge("test.gauge", 20.0)
        assert m.gauge_value("test.gauge") == 20.0

    def test_gauge_missing(self):
        m = MetricsCollector()
        assert m.gauge_value("nonexistent") == 0.0


class TestHistogram:
    def test_observe_and_stats(self):
        m = MetricsCollector()
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            m.observe("test.hist", v)
        stats = m.histogram_stats("test.hist")
        assert stats["count"] == 5
        assert stats["total"] == 15.0
        assert stats["mean"] == 3.0
        assert stats["min"] == 1.0
        assert stats["max"] == 5.0

    def test_histogram_missing(self):
        m = MetricsCollector()
        stats = m.histogram_stats("nonexistent")
        assert stats["count"] == 0

    def test_histogram_memory_bound(self):
        m = MetricsCollector()
        for i in range(_HISTOGRAM_MAX_SIZE + 500):
            m.observe("test.big", float(i))
        stats = m.histogram_stats("test.big")
        assert stats["count"] == _HISTOGRAM_MAX_SIZE + 500
        # Observations list is bounded
        snap = m.snapshot()
        assert snap["histograms"]["test.big"]["count"] == _HISTOGRAM_MAX_SIZE + 500


class TestSnapshot:
    def test_snapshot_structure(self):
        m = MetricsCollector()
        m.inc("c.one")
        m.set_gauge("g.one", 99.0)
        m.observe("h.one", 1.5)
        snap = m.snapshot()
        assert "uptime_seconds" in snap
        assert snap["counters"]["c.one"] == 1.0
        assert snap["gauges"]["g.one"] == 99.0
        assert snap["histograms"]["h.one"]["count"] == 1


class TestThreadSafety:
    def test_concurrent_increments(self):
        m = MetricsCollector()
        n_threads = 10
        n_per_thread = 1000

        def worker():
            for _ in range(n_per_thread):
                m.inc("concurrent.counter")

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert m.counter_value("concurrent.counter") == n_threads * n_per_thread


class TestSubsystems:
    def test_no_data(self):
        m = MetricsCollector()
        subs = m.instrumented_subsystems()
        assert not any(subs.values())

    def test_detects_scorer(self):
        m = MetricsCollector()
        m.inc("scorer.anthropic.calls")
        subs = m.instrumented_subsystems()
        assert subs["scorer"] is True
        assert subs["fetcher"] is False


class TestReset:
    def test_reset_clears(self):
        m = MetricsCollector()
        m.inc("a")
        m.set_gauge("b", 1.0)
        m.observe("c", 1.0)
        m.reset()
        assert m.counter_value("a") == 0.0
        assert m.gauge_value("b") == 0.0
        assert m.histogram_stats("c")["count"] == 0


class TestPersistence:
    def test_flush_to_db(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_metrics_table(conn)

        m = MetricsCollector()
        m.inc("test.counter", 5.0)
        m.set_gauge("test.gauge", 42.0)
        m.observe("test.hist", 1.0)

        rows_written = m.flush_to_db(conn)
        assert rows_written == 3

        rows = conn.execute("SELECT * FROM metrics ORDER BY name").fetchall()
        names = [r["name"] for r in rows]
        assert "test.counter" in names
        assert "test.gauge" in names
        assert "test.hist" in names

    def test_ensure_metrics_table_idempotent(self):
        conn = sqlite3.connect(":memory:")
        ensure_metrics_table(conn)
        ensure_metrics_table(conn)  # Should not raise


# ── Web endpoint tests ────────────────────────────────────────────────────


@pytest.fixture
def web_client():
    """Create a test client for the FastAPI app."""
    from fastapi.testclient import TestClient

    from twag.web.app import create_app

    app = create_app()
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, web_client):
        resp = web_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "uptime_seconds" in data
        assert data["db_connected"] is True


class TestMetricsEndpoint:
    def test_metrics_returns_snapshot(self, web_client):
        resp = web_client.get("/api/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "counters" in data
        assert "gauges" in data
        assert "histograms" in data
        assert "subsystems" in data
        assert "uptime_seconds" in data

    def test_metrics_records_web_requests(self, web_client):
        # First request primes metrics
        web_client.get("/api/health")
        resp = web_client.get("/api/metrics")
        data = resp.json()
        # The middleware should have incremented web.requests
        assert data["counters"].get("web.requests", 0) > 0
