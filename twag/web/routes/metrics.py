"""Health and metrics API endpoints."""

from __future__ import annotations

import sqlite3
import time

from fastapi import APIRouter, Request

from ... import __version__
from ...db import get_connection
from ...metrics import get_collector

router = APIRouter()

_START_TIME = time.monotonic()


@router.get("/health")
async def health(request: Request) -> dict:
    """Return service health: uptime, version, DB connectivity."""
    db_ok = False
    try:
        with get_connection(request.app.state.db_path, readonly=True) as conn:
            conn.execute("SELECT 1")
            db_ok = True
    except (sqlite3.Error, OSError):
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "uptime_seconds": round(time.monotonic() - _START_TIME, 2),
        "db_connected": db_ok,
    }


@router.get("/metrics")
async def metrics_snapshot() -> dict:
    """Return current in-memory metrics as JSON."""
    m = get_collector()
    snap = m.snapshot()
    snap["subsystems"] = m.instrumented_subsystems()
    return snap
