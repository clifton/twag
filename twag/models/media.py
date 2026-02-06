"""Pydantic models for tweet media items."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChartAnalysis(BaseModel):
    """Chart analysis from vision model."""

    type: str = ""
    description: str = ""
    insight: str = ""
    implication: str = ""
    tickers: list[str] = []


class TableAnalysis(BaseModel):
    """Table analysis from vision model."""

    title: str = ""
    description: str = ""
    columns: list[str] = []
    rows: list[list[str]] = []
    summary: str = ""
    tickers: list[str] = []


class MediaItem(BaseModel):
    """A single media item from a tweet."""

    url: str
    type: str = "photo"
    source: str | None = None
    media_id: Any = None
