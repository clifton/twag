"""Progress reporting for CLI commands."""

from __future__ import annotations

from typing import Protocol

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn


class ProgressReporter(Protocol):
    """Protocol for reporting progress from CLI commands."""

    def update_status(self, message: str) -> None: ...

    def advance(self, step: int = 1) -> None: ...

    def set_total(self, total: int) -> None: ...


class RichProgressReporter:
    """Rich-based progress reporter."""

    def __init__(self, progress: Progress, task_id: TaskID, label: str) -> None:
        self._progress = progress
        self._task_id = task_id
        self._label = label
        self._count = 0
        self._total = 0

    def update_status(self, message: str) -> None:
        self._label = message
        self._progress.update(
            self._task_id,
            description=f"{self._label} ({self._count}/{self._total})",
        )

    def advance(self, step: int = 1) -> None:
        if step < 0:
            step = 0
        self._count = min(self._total, self._count + step)
        self._progress.update(
            self._task_id,
            advance=step,
            description=f"{self._label} ({self._count}/{self._total})",
        )

    def set_total(self, total: int) -> None:
        if total < self._count:
            total = self._count
        self._total = total
        self._progress.update(
            self._task_id,
            total=total,
            description=f"{self._label} ({self._count}/{self._total})",
        )


class NullProgressReporter:
    """No-op progress reporter for non-interactive / library use."""

    def update_status(self, message: str) -> None:
        pass

    def advance(self, step: int = 1) -> None:
        pass

    def set_total(self, total: int) -> None:
        pass


def create_progress() -> Progress:
    """Create a standard Rich progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    )


def make_callbacks(reporter: ProgressReporter):
    """Return a (status_cb, progress_cb, total_cb) tuple from a ProgressReporter.

    This bridges the new ProgressReporter protocol to the legacy tuple-callback
    pattern that processor/fetcher commands expect.
    """
    return reporter.update_status, reporter.advance, reporter.set_total
