"""Metrics endpoint for operational visibility."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ...metrics import get_all_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics_endpoint() -> JSONResponse:
    """Return all collected metrics as JSON."""
    return JSONResponse(content=get_all_metrics())
