"""Helpers for selecting data-oriented visuals for article summaries."""

from __future__ import annotations

import re
from typing import Any

_DATA_KINDS = {"chart", "table", "document", "screenshot"}
_TEXTUAL_DATA_PATTERN = re.compile(
    r"\b(chart|graph|table|capex|revenue|margin|growth|yoy|qoq|forecast|projection|run[-\s]?rate|backlog|roi|ebitda|eps)\b"
)
_NUMERIC_DATA_PATTERN = re.compile(r"(\$|\b\d+(\.\d+)?%|\b\d+(\.\d+)?\s?(b|m|bn|mn|trillion|billion|million)\b)")
_NOISE_PATTERN = re.compile(r"\b(meme|reaction image|shitpost|joke|selfie|portrait)\b")


def _text_blob(*parts: Any) -> str:
    return " ".join(str(p).strip().lower() for p in parts if p is not None and str(p).strip())


def _looks_data_text(text: str) -> bool:
    if not text:
        return False
    if _NOISE_PATTERN.search(text):
        return False
    return bool(_TEXTUAL_DATA_PATTERN.search(text) or _NUMERIC_DATA_PATTERN.search(text))


def _infer_kind(item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or "").strip().lower()
    if kind in _DATA_KINDS:
        return kind
    if isinstance(item.get("chart"), dict) and (
        item["chart"].get("description") or item["chart"].get("insight") or item["chart"].get("implication")
    ):
        return "chart"
    if isinstance(item.get("table"), dict) and (item["table"].get("columns") or item["table"].get("summary")):
        return "table"
    text_blob = _text_blob(
        item.get("short_description"),
        item.get("prose_summary"),
        item.get("prose_text"),
        item.get("alt_text"),
    )
    if _looks_data_text(text_blob):
        return "chart"
    return kind


def _extract_takeaway(item: dict[str, Any], kind: str) -> str:
    if kind == "chart":
        raw_chart = item.get("chart")
        chart = raw_chart if isinstance(raw_chart, dict) else {}
        return str(chart.get("insight") or chart.get("implication") or chart.get("description") or "").strip()
    if kind == "table":
        raw_table = item.get("table")
        table = raw_table if isinstance(raw_table, dict) else {}
        return str(table.get("summary") or table.get("description") or "").strip()
    if kind in {"document", "screenshot"}:
        return str(item.get("prose_summary") or item.get("short_description") or "").strip()
    return str(item.get("short_description") or "").strip()


def _is_relevant_visual(item: dict[str, Any], kind: str) -> bool:
    if kind in _DATA_KINDS:
        return True
    text_blob = _text_blob(
        item.get("short_description"),
        item.get("prose_summary"),
        item.get("prose_text"),
        item.get("alt_text"),
    )
    return _looks_data_text(text_blob)


def build_article_visuals(
    *,
    top_visual: dict[str, Any] | None,
    media_items: list[dict[str, Any]] | None,
    max_items: int = 4,
) -> list[dict[str, Any]]:
    """Build ordered article visuals: top visual first, then other data visuals."""
    if max_items <= 0:
        return []

    visuals: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    if isinstance(top_visual, dict):
        top_url = str(top_visual.get("url") or "").strip()
        if top_url:
            why_important = str(top_visual.get("why_important") or "").strip()
            key_takeaway = str(top_visual.get("key_takeaway") or "").strip()
            top_kind = str(top_visual.get("kind") or "").strip().lower() or "visual"
            top_text = _text_blob(why_important, key_takeaway)
            if top_kind in _DATA_KINDS or _looks_data_text(top_text):
                visuals.append(
                    {
                        "url": top_url,
                        "kind": top_kind if top_kind in _DATA_KINDS else "chart",
                        "is_top": True,
                        "why_important": why_important,
                        "key_takeaway": key_takeaway,
                    }
                )
                seen_urls.add(top_url)

    extras: list[tuple[int, dict[str, Any]]] = []
    if isinstance(media_items, list):
        for item in media_items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            kind = _infer_kind(item)
            if not _is_relevant_visual(item, kind):
                continue
            takeaway = _extract_takeaway(item, kind)
            normalized_kind = kind if kind in _DATA_KINDS else "chart"
            priority = {"chart": 0, "table": 1, "screenshot": 2, "document": 3}.get(normalized_kind, 9)
            extras.append(
                (
                    priority,
                    {
                        "url": url,
                        "kind": normalized_kind,
                        "is_top": False,
                        "why_important": "",
                        "key_takeaway": takeaway,
                    },
                )
            )
            seen_urls.add(url)

    extras.sort(key=lambda pair: pair[0])
    for _, visual in extras:
        if len(visuals) >= max_items:
            break
        visuals.append(visual)

    return visuals
