"""Lightweight in-memory metrics collector with optional SQLite persistence.

No external dependencies — uses stdlib time and the existing SQLite connection.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import sqlite3


@dataclass
class _Counter:
    value: float = 0.0
    labels: dict[str, str] = field(default_factory=dict)

    def inc(self, amount: float = 1.0) -> None:
        self.value += amount


@dataclass
class _Gauge:
    value: float = 0.0
    labels: dict[str, str] = field(default_factory=dict)

    def set(self, value: float) -> None:
        self.value = value

    def inc(self, amount: float = 1.0) -> None:
        self.value += amount

    def dec(self, amount: float = 1.0) -> None:
        self.value -= amount


@dataclass
class _Histogram:
    """Simple histogram using fixed buckets."""

    buckets: tuple[float, ...] = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
    labels: dict[str, str] = field(default_factory=dict)
    _counts: list[int] = field(default_factory=list, init=False)
    _sum: float = field(default=0.0, init=False)
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        # +1 for the +Inf bucket
        self._counts = [0] * (len(self.buckets) + 1)

    def observe(self, value: float) -> None:
        self._sum += value
        self._count += 1
        for i, bound in enumerate(self.buckets):
            if value <= bound:
                self._counts[i] += 1
                return
        self._counts[-1] += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "count": self._count,
            "sum": self._sum,
            "mean": self._sum / self._count if self._count else 0.0,
            "buckets": {str(b): self._counts[i] for i, b in enumerate(self.buckets)},
            "inf": self._counts[-1],
        }


# ---------------------------------------------------------------------------
# Metrics table DDL
# ---------------------------------------------------------------------------

METRICS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS metrics (
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    value REAL NOT NULL,
    labels_json TEXT,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name, recorded_at DESC);
"""


# ---------------------------------------------------------------------------
# MetricsCollector
# ---------------------------------------------------------------------------


class MetricsCollector:
    """Thread-safe in-memory metrics store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, _Counter] = {}
        self._gauges: dict[str, _Gauge] = {}
        self._histograms: dict[str, _Histogram] = {}
        self._start_time = time.monotonic()

    # -- Counter API --------------------------------------------------------

    def counter(self, name: str, labels: dict[str, str] | None = None) -> _Counter:
        key = self._key(name, labels)
        with self._lock:
            if key not in self._counters:
                self._counters[key] = _Counter(labels=labels or {})
            return self._counters[key]

    def inc(self, name: str, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        self.counter(name, labels).inc(amount)

    # -- Gauge API ----------------------------------------------------------

    def gauge(self, name: str, labels: dict[str, str] | None = None) -> _Gauge:
        key = self._key(name, labels)
        with self._lock:
            if key not in self._gauges:
                self._gauges[key] = _Gauge(labels=labels or {})
            return self._gauges[key]

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        self.gauge(name, labels).set(value)

    # -- Histogram API ------------------------------------------------------

    def histogram(
        self,
        name: str,
        labels: dict[str, str] | None = None,
        buckets: tuple[float, ...] | None = None,
    ) -> _Histogram:
        key = self._key(name, labels)
        with self._lock:
            if key not in self._histograms:
                kwargs: dict[str, Any] = {"labels": labels or {}}
                if buckets is not None:
                    kwargs["buckets"] = buckets
                self._histograms[key] = _Histogram(**kwargs)
            return self._histograms[key]

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        self.histogram(name, labels).observe(value)

    # -- Timing context manager ---------------------------------------------

    def timer(self, name: str, labels: dict[str, str] | None = None) -> _Timer:
        return _Timer(self, name, labels)

    # -- Snapshot / export --------------------------------------------------

    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_time

    def snapshot(self) -> dict[str, Any]:
        """Return all metrics as a JSON-serializable dict."""
        with self._lock:
            result: dict[str, Any] = {
                "uptime_seconds": round(self.uptime_seconds(), 2),
                "counters": {},
                "gauges": {},
                "histograms": {},
            }
            for key, c in self._counters.items():
                result["counters"][key] = {"value": c.value, "labels": c.labels}
            for key, g in self._gauges.items():
                result["gauges"][key] = {"value": g.value, "labels": g.labels}
            for key, h in self._histograms.items():
                snap = h.snapshot()
                snap["labels"] = h.labels
                result["histograms"][key] = snap
            return result

    def persist(self, conn: sqlite3.Connection) -> int:
        """Write current metrics to the metrics table. Returns rows written."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rows: list[tuple[str, str, float, str | None, str]] = []

        with self._lock:
            for key, c in self._counters.items():
                labels_json = json.dumps(c.labels) if c.labels else None
                rows.append((key, "counter", c.value, labels_json, now))
            for key, g in self._gauges.items():
                labels_json = json.dumps(g.labels) if g.labels else None
                rows.append((key, "gauge", g.value, labels_json, now))
            for key, h in self._histograms.items():
                labels_json = json.dumps(h.labels) if h.labels else None
                rows.append((key, "histogram", h._sum, labels_json, now))

        if not rows:
            return 0

        conn.executemany(
            "INSERT INTO metrics (name, type, value, labels_json, recorded_at) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        return len(rows)

    def reset(self) -> None:
        """Clear all metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._start_time = time.monotonic()

    def subsystem_coverage(self) -> dict[str, bool]:
        """Report which subsystems have metrics instrumented."""
        with self._lock:
            all_keys = set(self._counters.keys()) | set(self._gauges.keys()) | set(self._histograms.keys())

        subsystems = {
            "scorer": "llm_",
            "pipeline": "pipeline_",
            "fetcher": "fetch_",
            "web": "http_",
            "triage": "triage_",
        }
        return {name: any(k.startswith(prefix) for k in all_keys) for name, prefix in subsystems.items()}

    # -- Internals ----------------------------------------------------------

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None) -> str:
        if not labels:
            return name
        sorted_labels = sorted(labels.items())
        suffix = ",".join(f"{k}={v}" for k, v in sorted_labels)
        return f"{name}{{{suffix}}}"


class _Timer:
    """Context manager that records elapsed time to a histogram."""

    def __init__(self, collector: MetricsCollector, name: str, labels: dict[str, str] | None) -> None:
        self._collector = collector
        self._name = name
        self._labels = labels
        self._start: float = 0.0

    def __enter__(self) -> _Timer:
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: object) -> None:
        elapsed = time.monotonic() - self._start
        self._collector.observe(self._name, elapsed, self._labels)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_collector = MetricsCollector()


def get_collector() -> MetricsCollector:
    """Return the global MetricsCollector singleton."""
    return _collector


def ensure_metrics_table(conn: sqlite3.Connection) -> None:
    """Create the metrics table if it doesn't exist."""
    conn.executescript(METRICS_TABLE_DDL)
