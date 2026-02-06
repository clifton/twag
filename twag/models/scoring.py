"""Pydantic models for LLM scoring and analysis results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator


class TriageResult(BaseModel):
    """Result of tweet triage scoring."""

    tweet_id: str
    score: float
    categories: list[str] = []
    summary: str = ""
    tickers: list[str] = []

    @field_validator("score")
    @classmethod
    def clamp_score(cls, v: float) -> float:
        return max(0.0, min(10.0, float(v)))


class EnrichmentResult(BaseModel):
    """Result of tweet enrichment analysis."""

    signal_tier: str = "noise"
    insight: str = ""
    implications: str = ""
    narratives: list[str] = []
    tickers: list[str] = []


class VisionResult(BaseModel):
    """Result of chart/image analysis."""

    chart_type: str = ""
    description: str = ""
    insight: str = ""
    implication: str = ""
    tickers: list[str] = []


class MediaAnalysisResult(BaseModel):
    """Result of image/media analysis."""

    kind: str = "other"
    short_description: str = ""
    prose_text: str = ""
    prose_summary: str = ""
    chart: dict[str, Any] = {}
    table: dict[str, Any] = {}


class PrimaryPoint(BaseModel):
    """A primary point from an X article summary."""

    point: str
    reasoning: str = ""
    evidence: str = ""


class ActionableItem(BaseModel):
    """An actionable item from an X article summary."""

    action: str
    trigger: str = ""
    horizon: str = ""
    confidence: float = 0.0
    tickers: list[str] = []

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class XArticleSummaryResult(BaseModel):
    """Structured summary for X native article payloads."""

    short_summary: str = ""
    primary_points: list[dict[str, Any]] = []
    actionable_items: list[dict[str, Any]] = []
