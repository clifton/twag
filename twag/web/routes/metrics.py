"""Health and metrics API endpoints."""

import sqlite3
from typing import Any

from fastapi import APIRouter, Request

from ... import __version__
from ...metrics import get_collector

router = APIRouter(tags=["metrics"])


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    """Return service health: uptime, version, DB connectivity."""
    collector = get_collector()
    db_ok = False
    try:
        db_path = request.app.state.db_path
        conn = sqlite3.connect(str(db_path), timeout=2)
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "uptime_seconds": round(collector.uptime_seconds(), 2),
        "db_connected": db_ok,
    }


@router.get("/metrics")
async def metrics() -> dict[str, Any]:
    """Return current in-memory metrics snapshot."""
    collector = get_collector()
    return collector.snapshot()
