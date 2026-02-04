"""Utilities for parsing and formatting tweet media."""

from __future__ import annotations

import json
from typing import Any


def parse_media_items(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict) and "items" in data:
        items = data.get("items", [])
    elif isinstance(data, list):
        items = data
    else:
        items = []

    cleaned: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cleaned.append(item)
    return cleaned


def build_media_summary(items: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in items:
        prose_summary = (item.get("prose_summary") or "").strip()
        short_description = (item.get("short_description") or "").strip()
        chart = item.get("chart") or {}
        chart_description = (chart.get("description") or "").strip()

        if prose_summary:
            parts.append(prose_summary)
        elif chart_description:
            parts.append(f"Chart: {chart_description}")
        elif short_description:
            parts.append(short_description)

    return " | ".join(parts)


def build_media_context(items: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for idx, item in enumerate(items, start=1):
        kind = item.get("kind") or "image"
        prose_text = (item.get("prose_text") or "").strip()
        short_description = (item.get("short_description") or "").strip()
        chart = item.get("chart") or {}
        chart_description = (chart.get("description") or "").strip()
        chart_insight = (chart.get("insight") or "").strip()
        chart_implication = (chart.get("implication") or "").strip()

        header = f"Media {idx} ({kind})"
        body_lines: list[str] = []

        if prose_text:
            body_lines.append("Document text:")
            body_lines.append(prose_text)
        elif chart_description or chart_insight or chart_implication:
            body_lines.append(f"Chart description: {chart_description}")
            if chart_insight:
                body_lines.append(f"Chart insight: {chart_insight}")
            if chart_implication:
                body_lines.append(f"Chart implication: {chart_implication}")
        elif short_description:
            body_lines.append(f"Image description: {short_description}")

        if body_lines:
            sections.append(f"{header}\n" + "\n".join(body_lines))

    return "\n\n".join(sections)
