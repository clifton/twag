"""Progress reporting for CLI commands."""

from __future__ import annotations

from typing import Protocol

from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn


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

    def _description(self) -> str:
        """Return the fixed-width task description for the progress bar."""
        return f"{self._label:<25s}"

    def update_status(self, message: str) -> None:
        """Update the progress bar description text."""
        self._label = message
        self._progress.update(self._task_id, description=self._description())

    def advance(self, step: int = 1) -> None:
        """Advance the progress bar by *step* units (clamped to total)."""
        step = max(step, 0)
        self._count = min(self._total, self._count + step)
        self._progress.update(self._task_id, advance=step, description=self._description())

    def set_total(self, total: int) -> None:
        """Set the expected total, ensuring it is at least the current count."""
        total = max(total, self._count)
        self._total = total
        self._progress.update(self._task_id, total=total, description=self._description())


class NullProgressReporter:
    """No-op progress reporter for non-interactive / library use."""

    def update_status(self, message: str) -> None:
        """No-op: ignore status updates."""

    def advance(self, step: int = 1) -> None:
        """No-op: ignore progress advances."""

    def set_total(self, total: int) -> None:
        """No-op: ignore total changes."""


def create_progress() -> Progress:
    """Create a standard Rich progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    )


def make_callbacks(reporter: ProgressReporter):
    """Return a (status_cb, progress_cb, total_cb) tuple from a ProgressReporter.

    This bridges the new ProgressReporter protocol to the legacy tuple-callback
    pattern that processor/fetcher commands expect.
    """
    return reporter.update_status, reporter.advance, reporter.set_total
