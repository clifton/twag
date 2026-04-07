"""Thread-safe in-memory metrics helpers for lightweight instrumentation."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock
from typing import TypedDict

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
class _HistogramSummary:
    count: int = 0
    total: float = 0.0
    min: float | None = None
    max: float | None = None

    def observe(self, value: float) -> None:
        self.count += 1
        self.total += value
        self.min = value if self.min is None else min(self.min, value)
        self.max = value if self.max is None else max(self.max, value)

    def snapshot(self) -> HistogramSnapshot:
        if self.count == 0 or self.min is None or self.max is None:
            return {"count": 0, "min": 0.0, "max": 0.0, "avg": 0.0, "total": 0.0}
        return {
            "count": self.count,
            "min": self.min,
            "max": self.max,
            "avg": self.total / self.count,
            "total": self.total,
        }


_lock = RLock()
_counters: dict[str, float] = {}
_histograms: dict[str, _HistogramSummary] = {}


def _label_key(name: str, labels: LabelMap | None = None) -> str:
    if not labels:
        return name
    ordered = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
    return f"{name}{{{ordered}}}"


def counter(name: str, *, value: float = 1.0, labels: LabelMap | None = None) -> float:
    key = _label_key(name, labels)
    with _lock:
        total = _counters.get(key, 0.0) + value
        _counters[key] = total
        return total


def histogram(name: str, value: float, *, labels: LabelMap | None = None) -> HistogramSnapshot:
    key = _label_key(name, labels)
    with _lock:
        summary = _histograms.setdefault(key, _HistogramSummary())
        summary.observe(value)
        return summary.snapshot()


@contextmanager
def timer(name: str, *, labels: LabelMap | None = None) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        histogram(name, time.perf_counter() - start, labels=labels)


def get_all_metrics() -> MetricsSnapshot:
    with _lock:
        counters = dict(_counters)
        histograms = {key: summary.snapshot() for key, summary in _histograms.items()}
    return {"counters": counters, "histograms": histograms}


def dump_json(path: str | None = None) -> str:
    payload = json.dumps(get_all_metrics(), indent=2, sort_keys=True)
    if path is not None:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)
    return payload


def reset() -> None:
    with _lock:
        _counters.clear()
        _histograms.clear()
