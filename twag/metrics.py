"""Lightweight, dependency-free metrics collection for twag.

Provides counters, gauges, and histograms stored in-memory with optional
SQLite persistence. Thread-safe via a single lock. No external dependencies.

Two API styles:
- Class-based: ``get_collector()`` returns a ``MetricsCollector`` singleton
- Module-level convenience: ``counter()``, ``histogram()``, ``timer()``, etc.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    import sqlite3

# Avoid shadowing builtins in dataclass methods
_min = min
_max = max

# Maximum number of observations kept per histogram to bound memory.
_HISTOGRAM_MAX_SIZE = 1000

# Schema for the metrics persistence table.
METRICS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS metrics (
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    value REAL NOT NULL,
    labels_json TEXT,
    recorded_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name, recorded_at DESC);
"""

LabelMap = Mapping[str, str]


class HistogramSnapshot(TypedDict):
    count: int
    min: float
    max: float
    avg: float
    total: float


class MetricsSnapshot(TypedDict):
    counters: dict[str, float]
    histograms: dict[str, HistogramSnapshot]


@dataclass
class _Counter:
    value: float = 0.0


@dataclass
class _Gauge:
    value: float = 0.0


@dataclass
class _Histogram:
    observations: list[float] = field(default_factory=list)
    count: int = 0
    total: float = 0.0
    min_val: float | None = None
    max_val: float | None = None

    def observe(self, value: float) -> None:
        self.count += 1
        self.total += value
        self.min_val = value if self.min_val is None else _min(self.min_val, value)
        self.max_val = value if self.max_val is None else _max(self.max_val, value)
        if len(self.observations) < _HISTOGRAM_MAX_SIZE:
            self.observations.append(value)
        else:
            # Rotate: drop oldest quarter, keep newest observations
            trim = _HISTOGRAM_MAX_SIZE // 4
            self.observations = self.observations[trim:]
            self.observations.append(value)

    def snapshot(self) -> HistogramSnapshot:
        if self.count == 0 or self.min_val is None or self.max_val is None:
            return {"count": 0, "min": 0.0, "max": 0.0, "avg": 0.0, "total": 0.0}
        return {
            "count": self.count,
            "min": self.min_val,
            "max": self.max_val,
            "avg": self.total / self.count,
            "total": self.total,
        }


class MetricsCollector:
    """In-memory metrics store with optional SQLite flush."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, _Counter] = {}
        self._gauges: dict[str, _Gauge] = {}
        self._histograms: dict[str, _Histogram] = {}
        self._last_flushed_counters: dict[str, float] = {}
        self._last_flushed_hist_counts: dict[str, int] = {}
        self._start_time = time.monotonic()

    # -- Counters --

    def inc(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = _Counter()
            self._counters[name].value += value

    def counter_value(self, name: str) -> float:
        with self._lock:
            c = self._counters.get(name)
            return c.value if c else 0.0

    # -- Gauges --

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = _Gauge()
            self._gauges[name].value = value

    def gauge_value(self, name: str) -> float:
        with self._lock:
            g = self._gauges.get(name)
            return g.value if g else 0.0

    # -- Histograms --

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = _Histogram()
            self._histograms[name].observe(value)

    def histogram_stats(self, name: str) -> dict[str, float]:
        with self._lock:
            h = self._histograms.get(name)
            if not h or h.count == 0:
                return {"count": 0, "total": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0, "p50": 0.0, "p99": 0.0}
            obs = sorted(h.observations)
            n = len(obs)
            return {
                "count": h.count,
                "total": h.total,
                "mean": h.total / h.count,
                "min": obs[0],
                "max": obs[-1],
                "p50": obs[n // 2],
                "p99": obs[_min(int(n * 0.99), n - 1)],
            }

    # -- Snapshot --

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            result: dict[str, Any] = {
                "uptime_seconds": time.monotonic() - self._start_time,
                "counters": {k: v.value for k, v in self._counters.items()},
                "gauges": {k: v.value for k, v in self._gauges.items()},
                "histograms": {},
            }
            for k, h in self._histograms.items():
                if h.count == 0:
                    continue
                obs = sorted(h.observations)
                n = len(obs)
                result["histograms"][k] = {
                    "count": h.count,
                    "total": h.total,
                    "mean": h.total / h.count,
                    "min": obs[0],
                    "max": obs[-1],
                    "p50": obs[n // 2],
                    "p99": obs[_min(int(n * 0.99), n - 1)],
                }
            return result

    # -- Subsystem coverage --

    def instrumented_subsystems(self) -> dict[str, bool]:
        """Return which subsystems have recorded at least one metric."""
        with self._lock:
            all_names = set(self._counters) | set(self._gauges) | set(self._histograms)

        prefixes = {
            "scorer": "scorer.",
            "pipeline": "pipeline.",
            "fetcher": "fetcher.",
            "web": "web.",
        }
        return {subsystem: any(n.startswith(prefix) for n in all_names) for subsystem, prefix in prefixes.items()}

    # -- Persistence --

    def flush_to_db(self, conn: sqlite3.Connection) -> int:
        """Persist deltas since last flush. Returns rows written.

        Counter rows store the *delta* between the current cumulative value and
        the value at the previous flush from this collector instance. This lets
        ``SUM(value)`` over a window across many process lifetimes recover the
        true total — cumulative-counter rows would lose data on process
        restart and double-count within a single process.

        Histograms write a row only when the count has advanced. Gauges always
        write the latest value (snapshot semantics).
        """
        with self._lock:
            snap = self.snapshot()
            rows: list[tuple[str, str, float, str | None]] = []

            for name, value in snap["counters"].items():
                last = self._last_flushed_counters.get(name, 0.0)
                delta = value - last
                if delta == 0:
                    continue
                rows.append((name, "counter", delta, None))
                self._last_flushed_counters[name] = value

            for name, value in snap["gauges"].items():
                rows.append((name, "gauge", value, None))

            for name, stats in snap["histograms"].items():
                count = int(stats["count"])
                last_count = self._last_flushed_hist_counts.get(name, 0)
                if count <= last_count:
                    continue
                rows.append((name, "histogram", stats["mean"], json.dumps(stats)))
                self._last_flushed_hist_counts[name] = count

            if rows:
                conn.executemany(
                    "INSERT INTO metrics (name, type, value, labels_json) VALUES (?, ?, ?, ?)",
                    rows,
                )
                conn.commit()
            return len(rows)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._last_flushed_counters.clear()
            self._last_flushed_hist_counts.clear()
            self._start_time = time.monotonic()


def ensure_metrics_table(conn: sqlite3.Connection) -> None:
    """Create the metrics table if it doesn't exist."""
    conn.executescript(METRICS_TABLE_SQL)


# Global singleton
_collector = MetricsCollector()


def get_collector() -> MetricsCollector:
    """Return the global MetricsCollector instance."""
    return _collector


# ── Module-level convenience API (thin wrappers around the singleton) ────


def _label_key(name: str, labels: LabelMap | None = None) -> str:
    if not labels:
        return name
    ordered = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
    return f"{name}{{{ordered}}}"


def counter(name: str, *, value: float = 1.0, labels: LabelMap | None = None) -> float:
    key = _label_key(name, labels)
    _collector.inc(key, value)
    return _collector.counter_value(key)


def histogram(name: str, value: float, *, labels: LabelMap | None = None) -> HistogramSnapshot:
    key = _label_key(name, labels)
    _collector.observe(key, value)
    stats = _collector.histogram_stats(key)
    return {
        "count": int(stats["count"]),
        "min": stats["min"],
        "max": stats["max"],
        "avg": stats["mean"],
        "total": stats["total"],
    }


@contextmanager
def timer(name: str, *, labels: LabelMap | None = None) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        histogram(name, time.perf_counter() - start, labels=labels)


def get_all_metrics() -> MetricsSnapshot:
    snap = _collector.snapshot()
    counters = dict(snap["counters"])
    histograms: dict[str, HistogramSnapshot] = {}
    for key, stats in snap["histograms"].items():
        histograms[key] = {
            "count": int(stats["count"]),
            "min": stats["min"],
            "max": stats["max"],
            "avg": stats["mean"],
            "total": stats["total"],
        }
    return {"counters": counters, "histograms": histograms}


def dump_json(path: str | None = None) -> str:
    payload = json.dumps(get_all_metrics(), indent=2, sort_keys=True)
    if path is not None:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)
    return payload


def reset() -> None:
    _collector.reset()


def flush_metrics() -> int:
    """Persist the current in-memory metrics to the twag SQLite database.

    Used by long-running CLI commands and the web layer to make in-memory
    counters visible to ``twag costs --since <window>``. Errors are swallowed
    (e.g. database missing or locked) so a flush failure never breaks the
    user's command — the in-memory snapshot is still available for the
    current process.
    """
    try:
        from .db import get_connection

        with get_connection() as conn:
            ensure_metrics_table(conn)
            return _collector.flush_to_db(conn)
    except Exception:
        return 0
