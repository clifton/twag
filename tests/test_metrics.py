"""Tests for twag.metrics module."""

import threading

import pytest

from twag.metrics import Counter, Gauge, Histogram, counter, gauge, get_all_metrics, histogram, reset_all


@pytest.fixture(autouse=True)
def _clean_metrics():
    """Reset global metrics state before each test."""
    reset_all()
    yield
    reset_all()


class TestCounter:
    def test_increment_default(self):
        c = Counter("test")
        c.inc()
        assert c.value == 1.0

    def test_increment_custom(self):
        c = Counter("test")
        c.inc(5)
        assert c.value == 5.0

    def test_multiple_increments(self):
        c = Counter("test")
        c.inc(2)
        c.inc(3)
        assert c.value == 5.0


class TestHistogram:
    def test_observe(self):
        h = Histogram("test")
        h.observe(1.5)
        h.observe(2.5)
        snap = h.snapshot
        assert snap["count"] == 2
        assert snap["sum"] == 4.0
        assert snap["min"] == 1.5
        assert snap["max"] == 2.5
        assert snap["avg"] == 2.0

    def test_empty_snapshot(self):
        h = Histogram("test")
        snap = h.snapshot
        assert snap["count"] == 0
        assert snap["avg"] == 0.0

    def test_time_context_manager(self):
        h = Histogram("test")
        with h.time():
            pass  # near-zero duration
        assert h.snapshot["count"] == 1
        assert h.snapshot["sum"] >= 0


class TestGauge:
    def test_set(self):
        g = Gauge("test")
        g.set(42)
        assert g.value == 42.0

    def test_inc_dec(self):
        g = Gauge("test")
        g.inc(10)
        g.dec(3)
        assert g.value == 7.0


class TestRegistry:
    def test_counter_registry(self):
        c = counter("my_counter")
        c.inc()
        assert counter("my_counter").value == 1.0

    def test_histogram_registry(self):
        h = histogram("my_hist")
        h.observe(5)
        assert histogram("my_hist").snapshot["count"] == 1

    def test_gauge_registry(self):
        g = gauge("my_gauge")
        g.set(99)
        assert gauge("my_gauge").value == 99.0


class TestGetAllMetrics:
    def test_export_structure(self):
        counter("c1").inc()
        histogram("h1").observe(1.0)
        gauge("g1").set(5)

        data = get_all_metrics()
        assert "counters" in data
        assert "histograms" in data
        assert "gauges" in data
        assert data["counters"]["c1"] == 1.0
        assert data["histograms"]["h1"]["count"] == 1
        assert data["gauges"]["g1"] == 5.0

    def test_empty_export(self):
        data = get_all_metrics()
        assert data == {"counters": {}, "histograms": {}, "gauges": {}}


class TestThreadSafety:
    def test_concurrent_counter_increments(self):
        c = counter("concurrent")
        n_threads = 10
        n_increments = 1000

        def worker():
            for _ in range(n_increments):
                c.inc()

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert c.value == n_threads * n_increments

    def test_concurrent_histogram_observations(self):
        h = histogram("concurrent_hist")
        n_threads = 10
        n_obs = 100

        def worker():
            for i in range(n_obs):
                h.observe(float(i))

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert h.snapshot["count"] == n_threads * n_obs
