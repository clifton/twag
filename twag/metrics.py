"""Lightweight, dependency-free in-process metrics collection.

Provides Counter, Histogram, and Gauge primitives with thread-safe state.
All metrics are stored in module-level registries and exported via
``get_all_metrics()`` for JSON serialization.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Any

_lock = threading.Lock()
_counters: dict[str, Counter] = {}
_histograms: dict[str, Histogram] = {}
_gauges: dict[str, Gauge] = {}


class Counter:
    """Monotonically increasing counter."""

    __slots__ = ("_lock", "_value", "name")

    def __init__(self, name: str) -> None:
        self.name = name
        self._value: float = 0.0
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    @property
    def value(self) -> float:
        with self._lock:
            return self._value


class Histogram:
    """Records observations and exposes count, sum, min, max, and avg."""

    __slots__ = ("_count", "_lock", "_max", "_min", "_sum", "name")

    def __init__(self, name: str) -> None:
        self.name = name
        self._count: int = 0
        self._sum: float = 0.0
        self._min: float = float("inf")
        self._max: float = float("-inf")
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self._count += 1
            self._sum += value
            self._min = min(self._min, value)
            self._max = max(self._max, value)

    @property
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if self._count == 0:
                return {"count": 0, "sum": 0.0, "min": 0.0, "max": 0.0, "avg": 0.0}
            return {
                "count": self._count,
                "sum": round(self._sum, 4),
                "min": round(self._min, 4),
                "max": round(self._max, 4),
                "avg": round(self._sum / self._count, 4),
            }

    @contextmanager
    def time(self):
        """Context manager that records elapsed seconds as an observation."""
        start = time.monotonic()
        try:
            yield
        finally:
            self.observe(time.monotonic() - start)


class Gauge:
    """Point-in-time value that can go up or down."""

    __slots__ = ("_lock", "_value", "name")

    def __init__(self, name: str) -> None:
        self.name = name
        self._value: float = 0.0
        self._lock = threading.Lock()

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value -= amount

    @property
    def value(self) -> float:
        with self._lock:
            return self._value


def counter(name: str) -> Counter:
    """Get or create a named counter."""
    with _lock:
        if name not in _counters:
            _counters[name] = Counter(name)
        return _counters[name]


def histogram(name: str) -> Histogram:
    """Get or create a named histogram."""
    with _lock:
        if name not in _histograms:
            _histograms[name] = Histogram(name)
        return _histograms[name]


def gauge(name: str) -> Gauge:
    """Get or create a named gauge."""
    with _lock:
        if name not in _gauges:
            _gauges[name] = Gauge(name)
        return _gauges[name]


def get_all_metrics() -> dict[str, Any]:
    """Export all registered metrics as a JSON-serializable dict."""
    with _lock:
        counters_snapshot = {name: c.value for name, c in sorted(_counters.items())}
        histograms_snapshot = {name: h.snapshot for name, h in sorted(_histograms.items())}
        gauges_snapshot = {name: g.value for name, g in sorted(_gauges.items())}
    return {
        "counters": counters_snapshot,
        "histograms": histograms_snapshot,
        "gauges": gauges_snapshot,
    }


def reset_all() -> None:
    """Clear all metrics. Intended for testing only."""
    with _lock:
        _counters.clear()
        _histograms.clear()
        _gauges.clear()
