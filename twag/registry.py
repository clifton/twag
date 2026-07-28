"""Read-only helpers for annotating signals from the spine-owned registry."""

import json
from pathlib import Path
from typing import Any

REGISTRY_DIR = Path.home() / "clawd" / "state" / "registry"
POSITION_RELATIONSHIPS = {"owned", "short", "watchlist", "expression"}


def _load_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _format_match(instrument: dict[str, Any], shared_theme: str | None = None) -> str:
    ticker = str(instrument.get("ticker") or "").upper()
    relationship = str(instrument.get("relationship") or "").replace("_", " ")
    details = [relationship] if relationship else []
    if shared_theme:
        details.append(shared_theme)
    suffix = f" ({', '.join(details)})" if details else ""
    return f"{ticker}{suffix}"


def match_positions(
    themes: list[str] | None,
    tickers: list[str] | None,
    *,
    registry_dir: Path | None = None,
) -> str | None:
    """Return one exact-ticker or shared-theme book match, never a broad match."""
    root = registry_dir or REGISTRY_DIR
    instruments_payload = _load_object(root / "instruments.json")
    themes_payload = _load_object(root / "themes.json")
    if not instruments_payload or not themes_payload:
        return None

    instruments = instruments_payload.get("instruments")
    registry_themes = themes_payload.get("themes")
    if not isinstance(instruments, list) or not isinstance(registry_themes, list):
        return None

    positioned = [
        item
        for item in instruments
        if isinstance(item, dict) and item.get("relationship") in POSITION_RELATIONSHIPS and item.get("ticker")
    ]
    ticker_set = {str(ticker).upper() for ticker in tickers or []}
    for instrument in positioned:
        if str(instrument["ticker"]).upper() in ticker_set:
            instrument_themes = instrument.get("themes") if isinstance(instrument.get("themes"), list) else []
            shared = next((theme for theme in themes or [] if theme in instrument_themes), None)
            return _format_match(instrument, shared)

    valid_theme_ids = {
        str(item["id"])
        for item in registry_themes
        if isinstance(item, dict) and item.get("id") and item.get("status") != "closed"
    }
    signal_themes = [theme for theme in themes or [] if theme in valid_theme_ids]
    for theme in signal_themes:
        for instrument in positioned:
            instrument_themes = instrument.get("themes") if isinstance(instrument.get("themes"), list) else []
            if theme in instrument_themes:
                return _format_match(instrument, theme)
    return None
