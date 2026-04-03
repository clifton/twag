"""Lightweight in-memory metrics module using only stdlib.

Provides counters and histograms with optional label dimensions.
Histograms use a bounded running-summary approach (count/sum/min/max)
to avoid unbounded memory growth.

Thread-safe via a single module-level lock.
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Counter:
    value: float = 0.0


@dataclass
class _Histogram:
    """Running summary — no per-observation storage."""

    count: int = 0
    total: float = 0.0
    min: float = field(default=float("inf"))
    max: float = field(default=float("-inf"))

    def observe(self, value: float) -> None:
        self.count += 1
        self.total += value
        self.min = min(self.min, value)
        self.max = max(self.max, value)

    def snapshot(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "total": round(self.total, 6),
            "min": round(self.min, 6) if self.count > 0 else None,
            "max": round(self.max, 6) if self.count > 0 else None,
            "avg": round(self.total / self.count, 6) if self.count > 0 else None,
        }


_lock = threading.Lock()
_counters: dict[str, _Counter] = {}
_histograms: dict[str, _Histogram] = {}


def _label_key(name: str, labels: dict[str, str] | None = None) -> str:
    if not labels:
        return name
    parts = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    return f"{name}{{{parts}}}"


def counter(name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
    """Increment a counter by *value* (default 1)."""
    key = _label_key(name, labels)
    with _lock:
        if key not in _counters:
            _counters[key] = _Counter()
        _counters[key].value += value


def histogram(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    """Record an observation in a histogram (running summary)."""
    key = _label_key(name, labels)
    with _lock:
        if key not in _histograms:
            _histograms[key] = _Histogram()
        _histograms[key].observe(value)


@contextmanager
def timer(name: str, labels: dict[str, str] | None = None):
    """Context manager that records elapsed seconds into a histogram."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        histogram(name, elapsed, labels)


def get_all_metrics() -> dict[str, Any]:
    """Return a snapshot of all counters and histograms."""
    with _lock:
        counters = {k: v.value for k, v in sorted(_counters.items())}
        histograms = {k: v.snapshot() for k, v in sorted(_histograms.items())}
    return {"counters": counters, "histograms": histograms}


def reset() -> None:
    """Clear all metrics. Intended for testing."""
    with _lock:
        _counters.clear()
        _histograms.clear()


def dump_json(path: str | None = None) -> str:
    """Serialize current metrics to JSON. Optionally write to *path*."""
    data = get_all_metrics()
    text = json.dumps(data, indent=2)
    if path:
        with open(path, "w") as f:
            f.write(text)
    return text
