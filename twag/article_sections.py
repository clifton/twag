"""Shared parsing/normalization helpers for structured article sections."""

from __future__ import annotations

import json
from typing import Any


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return decoded if isinstance(decoded, list) else []


def normalize_horizon(value: Any) -> str:
    text = str(value or "").strip()
    return text.replace("_", " ") if text else ""


def format_confidence(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value).strip()


def parse_primary_points(value: str | None, *, limit: int | None = None) -> list[dict[str, str]]:
    points: list[dict[str, str]] = []
    for item in _json_list(value):
        if not isinstance(item, dict):
            continue
        point = str(item.get("point") or "").strip()
        if not point:
            continue
        points.append(
            {
                "point": point,
                "reasoning": str(item.get("reasoning") or "").strip(),
                "evidence": str(item.get("evidence") or "").strip(),
            }
        )
        if limit is not None and len(points) >= limit:
            break
    return points


def parse_action_items(value: str | None, *, limit: int | None = None) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for item in _json_list(value):
        if not isinstance(item, dict):
            continue

        action = str(item.get("action") or "").strip()
        if not action:
            continue

        item_tickers = item.get("tickers")
        ticker_text = ""
        if isinstance(item_tickers, list):
            cleaned = [str(t).strip() for t in item_tickers if str(t).strip()]
            ticker_text = ", ".join(cleaned)

        actions.append(
            {
                "action": action,
                "trigger": str(item.get("trigger") or "").strip(),
                "horizon": normalize_horizon(item.get("horizon")),
                "confidence": format_confidence(item.get("confidence")),
                "tickers": ticker_text,
            }
        )
        if limit is not None and len(actions) >= limit:
            break
    return actions
