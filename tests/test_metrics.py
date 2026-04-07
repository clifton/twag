"""Tests for the metrics collector, health endpoint, and metrics endpoint."""

import sqlite3

import pytest

from twag.metrics import MetricsCollector, ensure_metrics_table, get_collector


class TestMetricsCollector:
    def test_counter_inc(self):
        m = MetricsCollector()
        m.inc("test_counter")
        m.inc("test_counter", 5)
        snap = m.snapshot()
        assert snap["counters"]["test_counter"]["value"] == 6

    def test_counter_with_labels(self):
        m = MetricsCollector()
        m.inc("calls", labels={"provider": "gemini"})
        m.inc("calls", labels={"provider": "anthropic"})
        snap = m.snapshot()
        assert "calls{provider=gemini}" in snap["counters"]
        assert "calls{provider=anthropic}" in snap["counters"]

    def test_gauge_set(self):
        m = MetricsCollector()
        m.set_gauge("active_requests", 42)
        snap = m.snapshot()
        assert snap["gauges"]["active_requests"]["value"] == 42

    def test_gauge_inc_dec(self):
        m = MetricsCollector()
        g = m.gauge("connections")
        g.inc(3)
        g.dec(1)
        assert g.value == 2

    def test_histogram_observe(self):
        m = MetricsCollector()
        m.observe("latency", 0.05)
        m.observe("latency", 0.5)
        m.observe("latency", 2.0)
        snap = m.snapshot()
        h = snap["histograms"]["latency"]
        assert h["count"] == 3
        assert h["sum"] == pytest.approx(2.55)
        assert h["mean"] == pytest.approx(0.85)

    def test_timer_context_manager(self):
        m = MetricsCollector()
        with m.timer("op_duration"):
            pass  # nearly instant
        snap = m.snapshot()
        assert snap["histograms"]["op_duration"]["count"] == 1
        assert snap["histograms"]["op_duration"]["sum"] >= 0

    def test_uptime(self):
        m = MetricsCollector()
        assert m.uptime_seconds() >= 0

    def test_reset(self):
        m = MetricsCollector()
        m.inc("x")
        m.reset()
        snap = m.snapshot()
        assert snap["counters"] == {}

    def test_persist_to_sqlite(self):
        m = MetricsCollector()
        m.inc("test_persist", 10)
        m.set_gauge("test_gauge", 3.14)
        m.observe("test_hist", 1.0)

        conn = sqlite3.connect(":memory:")
        ensure_metrics_table(conn)
        rows_written = m.persist(conn)
        assert rows_written == 3

        cursor = conn.execute("SELECT COUNT(*) FROM metrics")
        assert cursor.fetchone()[0] == 3
        conn.close()

    def test_subsystem_coverage_empty(self):
        m = MetricsCollector()
        coverage = m.subsystem_coverage()
        assert all(v is False for v in coverage.values())

    def test_subsystem_coverage_partial(self):
        m = MetricsCollector()
        m.inc("llm_calls_total")
        m.inc("fetch_calls_total")
        coverage = m.subsystem_coverage()
        assert coverage["scorer"] is True
        assert coverage["fetcher"] is True
        assert coverage["pipeline"] is False
        assert coverage["web"] is False
        assert coverage["triage"] is False

    def test_get_collector_singleton(self):
        c1 = get_collector()
        c2 = get_collector()
        assert c1 is c2


class TestHealthEndpoint:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        # Avoid importing bird CLI or other heavy deps
        monkeypatch.setenv("TWAG_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("TWAG_DB_PATH", str(tmp_path / "test.db"))

        from twag.db import init_db

        init_db(tmp_path / "test.db")

        from starlette.testclient import TestClient

        from twag.web.app import create_app

        app = create_app()
        # Override the db_path to our test db
        app.state.db_path = tmp_path / "test.db"
        return TestClient(app)

    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["db_connected"] is True
        assert "version" in data
        assert "uptime_seconds" in data


class TestMetricsEndpoint:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TWAG_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("TWAG_DB_PATH", str(tmp_path / "test.db"))

        from twag.db import init_db

        init_db(tmp_path / "test.db")

        from starlette.testclient import TestClient

        from twag.web.app import create_app

        app = create_app()
        app.state.db_path = tmp_path / "test.db"
        return TestClient(app)

    def test_metrics_returns_snapshot(self, client):
        # Record something so we can verify it shows up
        collector = get_collector()
        collector.inc("test_metric_endpoint", 42)

        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "counters" in data
        assert "gauges" in data
        assert "histograms" in data
        assert "uptime_seconds" in data
