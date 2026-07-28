"""CLI logging setup."""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import rich_click as click

from ..config import get_data_dir

_SENSITIVE_MARKERS = ("key", "token", "secret", "password", "auth", "ct0")
_HANDLER_ATTR = "_twag_cli_handler"


def _log_dir() -> Path:
    override = os.environ.get("TWAG_LOG_DIR")
    if override:
        return Path(override).expanduser()
    try:
        return get_data_dir() / "logs"
    except Exception:
        return Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser() / "twag" / "logs"


def _remove_cli_file_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_ATTR, False):
            root.removeHandler(handler)
            handler.close()


def _skip_default_logging_under_pytest() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) and not os.environ.get("TWAG_LOG_DIR")


def _redact_args(args: list[str]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    for arg in args:
        lowered = arg.lower()
        if redact_next:
            redacted.append("[REDACTED]")
            redact_next = False
            continue
        if any(marker in lowered for marker in _SENSITIVE_MARKERS):
            if "=" in arg:
                key, _value = arg.split("=", 1)
                redacted.append(f"{key}=[REDACTED]")
            else:
                redacted.append(arg)
                if arg.startswith("-"):
                    redact_next = True
            continue
        redacted.append(arg)
    return redacted


def configure_cli_logging() -> Path:
    """Configure file logging for CLI runs and library loggers."""
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"cli-{datetime.now().strftime('%Y-%m-%d')}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_ATTR, False):
            if Path(getattr(handler, "baseFilename", "")) == log_path:
                return log_path
            root.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(log_path, maxBytes=10_000_000, backupCount=7)
    setattr(handler, _HANDLER_ATTR, True)
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(process)d:%(threadName)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        ),
    )
    root.addHandler(handler)
    logging.captureWarnings(True)
    return log_path


def _exit_code(exc: SystemExit) -> int:
    if isinstance(exc.code, int):
        return exc.code
    return 1 if exc.code else 0


class LoggedGroup(click.RichGroup):
    """Rich click group that logs command lifecycle and unhandled failures."""

    def main(self, *args: Any, **kwargs: Any) -> Any:
        argv = kwargs.get("args")
        if argv is None:
            argv = sys.argv[1:]
        argv = list(argv)

        log_path: Path | None = None
        if _skip_default_logging_under_pytest():
            _remove_cli_file_handlers()
        else:
            log_path = configure_cli_logging()
        log = logging.getLogger("twag.cli")
        started = time.monotonic()
        command = " ".join(_redact_args(argv))
        if log_path is not None:
            log.info("command_start argv=%r cwd=%s log=%s", command, os.getcwd(), log_path)

        try:
            result = super().main(*args, **kwargs)
        except SystemExit as exc:
            code = _exit_code(exc)
            elapsed = time.monotonic() - started
            if log_path is not None:
                log.info("command_exit code=%s elapsed=%.3fs argv=%r", code, elapsed, command)
            raise
        except BaseException:
            elapsed = time.monotonic() - started
            if log_path is not None:
                log.exception("command_error elapsed=%.3fs argv=%r", elapsed, command)
            raise

        elapsed = time.monotonic() - started
        if log_path is not None:
            log.info("command_exit code=0 elapsed=%.3fs argv=%r", elapsed, command)
        return result
