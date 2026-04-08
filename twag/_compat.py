"""Backward-compatibility shims for APIs removed in v0.2.

Each shim re-exports or wraps the replacement API and emits a
DeprecationWarning directing callers to the new location.
Shims will be removed in v0.3.
"""

from __future__ import annotations

import warnings


def _deprecated(old: str, new: str, *, removal: str = "v0.3") -> None:
    """Emit a DeprecationWarning for a moved/removed API."""
    warnings.warn(
        f"{old} is deprecated and will be removed in {removal}. Use {new} instead.",
        DeprecationWarning,
        stacklevel=3,
    )
