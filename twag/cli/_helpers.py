"""Shared CLI utilities."""

import json
import re


def _normalize_status_id_or_url(status_id_or_url: str) -> str:
    """Normalize a status argument to a tweet ID when possible."""
    value = status_id_or_url.strip()
    if value.isdigit():
        return value

    match = re.search(r"/status/(\d+)", value)
    if match:
        return match.group(1)

    return value


def _json_list(value: str | None) -> list:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return decoded if isinstance(decoded, list) else []


def _json_object(value: str | None) -> dict:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}
