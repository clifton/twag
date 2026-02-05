"""Helpers for selecting data-oriented visuals for article summaries."""

from __future__ import annotations

from typing import Any

_DATA_KINDS = {"chart", "table", "document", "screenshot"}


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
    return kind


def _extract_takeaway(item: dict[str, Any], kind: str) -> str:
    if kind == "chart":
        chart = item.get("chart") if isinstance(item.get("chart"), dict) else {}
        return str(chart.get("insight") or chart.get("implication") or chart.get("description") or "").strip()
    if kind == "table":
        table = item.get("table") if isinstance(item.get("table"), dict) else {}
        return str(table.get("summary") or table.get("description") or "").strip()
    if kind in {"document", "screenshot"}:
        return str(item.get("prose_summary") or item.get("short_description") or "").strip()
    return str(item.get("short_description") or "").strip()


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
            top_kind = str(top_visual.get("kind") or "visual").strip().lower()
            visuals.append(
                {
                    "url": top_url,
                    "kind": top_kind,
                    "is_top": True,
                    "why_important": str(top_visual.get("why_important") or "").strip(),
                    "key_takeaway": str(top_visual.get("key_takeaway") or "").strip(),
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
            if kind not in _DATA_KINDS:
                continue
            takeaway = _extract_takeaway(item, kind)
            priority = {"chart": 0, "table": 1, "screenshot": 2, "document": 3}.get(kind, 9)
            extras.append(
                (
                    priority,
                    {
                        "url": url,
                        "kind": kind,
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
