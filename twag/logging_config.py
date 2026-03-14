"""Centralized logging configuration for twag."""

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """Set up root logger with a sensible format to stderr."""
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)
