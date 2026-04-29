"""Centralized logging configuration for twag CLI and web entrypoints."""

from __future__ import annotations

import logging
import os
from logging.config import dictConfig

DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DEFAULT_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"

_configured = False


def configure_logging(level: int | str | None = None, fmt: str | None = None) -> None:
    """Configure root logging for twag CLI/web entrypoints.

    Idempotent: safe to call multiple times (e.g., from both CLI and web app
    in a combined process). The LOG_LEVEL env var overrides ``level`` when set.
    """
    global _configured
    if _configured:
        return

    env_level = os.environ.get("LOG_LEVEL")
    resolved_level: int | str
    if env_level:
        resolved_level = env_level.upper()
    elif level is None:
        resolved_level = "INFO"
    else:
        resolved_level = level

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": fmt or DEFAULT_FORMAT,
                    "datefmt": DEFAULT_DATEFMT,
                },
            },
            "handlers": {
                "stderr": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": "ext://sys.stderr",
                },
            },
            "root": {
                "level": resolved_level,
                "handlers": ["stderr"],
            },
            "loggers": {
                "twag": {"level": resolved_level, "propagate": True},
            },
        },
    )
    _configured = True


def reset_for_tests() -> None:
    """Reset configuration state — used by tests that need a clean slate."""
    global _configured
    _configured = False
    logging.getLogger().handlers.clear()
