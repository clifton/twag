"""Deterministic signal-event emission for the spine-owned ledger."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .scorer import load_fund_context

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable

REGISTRY_DIR = Path.home() / "clawd" / "state" / "registry"
_THEME_RE = re.compile(r"^[a-z0-9-]{3,40}$")
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9./-]{0,15}$")
_PLAYBOOK_MAP = {
    "supply_shock": "supply_loss",
    "supercycle": "supercycle",
    "vol_substitution": "vol_substitution",
    "ai_victim": "ai_victim",
    "event_reset": "earnings_gap_reset",
    "dat_mnav": "dat_mnav",
    "defensive_break": "expensive_defensive",
}
_CATALYST_LABELS = {
    "FOMC": ("fomc", "us"),
    "NFP": ("nfp", "us"),
    "CPI": ("cpi", "us"),
    "PPI": ("ppi", "us"),
    "ECB": ("ecb", "eu"),
    "BOJ": ("boj", "jp"),
}


def _json_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in decoded] if isinstance(decoded, list) else []


def signal_id(tweet_id: str) -> str:
    """Return a deterministic schema-valid event id for a tweet."""
    digest = hashlib.sha256(f"twag:{tweet_id}".encode()).digest()[:12]
    token = base64.b32encode(digest).decode().rstrip("=")
    return f"sig_{token}"


def signal_kind(
    score: float,
    surprise: int,
    catalyst_status: str | None,
    *,
    catalyst_ref: str | None = None,
) -> str:
    """Map scoring facts to a schema-v1 kind without inventing catalyst ids."""
    if surprise == 2:
        return "surprise"
    if catalyst_status == "scheduled" and catalyst_ref:
        return "catalyst_scheduled"
    if catalyst_status == "resolved" and catalyst_ref:
        return "catalyst_resolved"
    return "datapoint"


def signal_materiality(score: float, playbook_trigger: str | None) -> int:
    """Map score/playbook state to the shared 1-3 materiality scale."""
    if playbook_trigger or score >= 9:
        return 3
    if score >= 8:
        return 2
    return 1


def _parse_event_ts(value: Any) -> datetime:
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _context_catalysts(fund_context: str, reference_year: int) -> list[tuple[str, str, str, str]]:
    marker = "UPCOMING CATALYSTS (14d):"
    line = next((line for line in fund_context.splitlines() if line.startswith(marker)), "")
    if not line:
        return []
    entries = []
    for raw_entry in line.removeprefix(marker).split("·"):
        entry = raw_entry.strip()
        full_date = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", entry)
        short_date = re.search(r"~?(\d{2})-(\d{2})", entry)
        if full_date:
            event_date = full_date.group(1)
        elif short_date:
            event_date = f"{reference_year:04d}-{short_date.group(1)}-{short_date.group(2)}"
        else:
            continue
        upper_entry = entry.upper()
        matched = next(((label, values) for label, values in _CATALYST_LABELS.items() if label in upper_entry), None)
        if matched:
            label, (catalyst_type, scope) = matched
            entries.append((label, catalyst_type, scope, event_date))
            continue
        earnings = re.search(r"\b([A-Z][A-Z0-9./-]{0,15})\s+EARNINGS\b", upper_entry)
        if earnings:
            ticker = earnings.group(1)
            entries.append((f"{ticker} EARNINGS", "earnings", ticker.lower(), event_date))
    return entries


def match_catalyst(
    row: sqlite3.Row | dict[str, Any],
    fund_context: str,
    *,
    registry_dir: Path | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Match a scheduled/resolved tweet to one unambiguous context catalyst."""
    if row["catalyst_status"] == "resolved":
        root = registry_dir or REGISTRY_DIR
        try:
            payload = json.loads((root / "catalysts.json").read_text())
        except (OSError, json.JSONDecodeError):
            payload = {}
        catalysts = payload.get("catalysts") if isinstance(payload, dict) else None
        tickers = set(_json_list(row["tickers"]))
        themes = set(_json_list(row["themes"]))
        ticker_matches = []
        theme_matches = []
        if isinstance(catalysts, list):
            for catalyst in catalysts:
                if not isinstance(catalyst, dict) or not catalyst.get("id"):
                    continue
                candidate = (str(catalyst["id"]), catalyst.get("date"), catalyst.get("type"))
                if tickers & set(_json_list(catalyst.get("instruments"))):
                    ticker_matches.append(candidate)
                elif themes & set(_json_list(catalyst.get("themes"))):
                    theme_matches.append(candidate)
        if len(ticker_matches) == 1:
            return ticker_matches[0]
        if not ticker_matches and len(theme_matches) == 1:
            return theme_matches[0]
        return None, None, None

    created_at = _parse_event_ts(row["created_at"])
    haystack = f"{row['summary'] or ''} {row['content'] or ''}".upper()
    matches = []
    for label, catalyst_type, scope, event_date in _context_catalysts(fund_context, created_at.year):
        if label in haystack:
            matches.append((f"{catalyst_type}:{scope}:{event_date}", event_date, catalyst_type))
    if len(matches) == 1:
        return matches[0]
    return None, None, None


def build_signal_event(
    row: sqlite3.Row | dict[str, Any],
    *,
    fund_context: str = "",
    registry_dir: Path | None = None,
) -> dict[str, Any]:
    """Build one canonical signal-event v1 object from a processed tweet."""
    score = float(row["relevance_score"] or 0)
    surprise = int(row["surprise"] or 0)
    catalyst_ref, catalyst_date, catalyst_type = match_catalyst(row, fund_context, registry_dir=registry_dir)
    kind = signal_kind(score, surprise, row["catalyst_status"], catalyst_ref=catalyst_ref)
    event_ts = _parse_event_ts(row["created_at"] or row["processed_at"])
    author = row["author_handle"] or "i"
    tweet_id = str(row["id"])
    summary = str(row["summary"] or row["content"] or "Market signal").strip().replace("\n", " ")
    one_liner = summary[:137].rstrip() + "..." if len(summary) > 140 else summary
    themes = list(dict.fromkeys(theme for theme in _json_list(row["themes"]) if _THEME_RE.fullmatch(theme)))
    instruments = list(
        dict.fromkeys(ticker.upper() for ticker in _json_list(row["tickers"]) if _TICKER_RE.fullmatch(ticker.upper())),
    )
    if registry_dir is not None:
        try:
            themes_payload = json.loads((registry_dir / "themes.json").read_text())
            instruments_payload = json.loads((registry_dir / "instruments.json").read_text())
            valid_themes = {
                str(item["id"])
                for item in themes_payload.get("themes", [])
                if isinstance(item, dict) and item.get("id")
            }
            valid_instruments = {
                str(item["ticker"]).upper()
                for item in instruments_payload.get("instruments", [])
                if isinstance(item, dict) and item.get("ticker")
            }
            themes = [theme for theme in themes if theme in valid_themes]
            instruments = [ticker for ticker in instruments if ticker in valid_instruments]
        except (OSError, json.JSONDecodeError, AttributeError):
            themes = []
            instruments = []
    direction = row["direction"] if row["direction"] in {"long", "short", "na"} else "na"
    playbook = _PLAYBOOK_MAP.get(row["playbook_trigger"])
    event: dict[str, Any] = {
        "id": signal_id(tweet_id),
        "schema_version": 1,
        "ts": event_ts.isoformat().replace("+00:00", "Z"),
        "source": "twag_digest",
        "urls": [f"https://x.com/{author}/status/{tweet_id}"],
        "one_liner": one_liner,
        "kind": kind,
        "direction": direction,
        "themes": themes,
        "instruments": instruments,
        "materiality": signal_materiality(score, row["playbook_trigger"]),
        "playbook_trigger": playbook,
        "catalyst_ref": catalyst_ref,
        "dedup_key": f"tweet:{tweet_id}",
        "dashboard_files_touched": [],
        "notion_sync": "pending",
        "correspondence": None,
        "action_item": None,
    }
    if kind == "catalyst_scheduled":
        event["catalyst_date"] = catalyst_date
        event["catalyst_type"] = catalyst_type
    return event


def append_signal_event(event: dict[str, Any], *, timeout_seconds: int = 60) -> None:
    """Append through the spine owner so validation, dedup, and views stay coherent."""
    spine_bin = shutil.which("spine")
    if not spine_bin:
        raise RuntimeError("spine CLI not found in PATH")
    command = [
        spine_bin,
        "signal",
        "append",
        "--source",
        str(event["source"]),
        "--kind",
        str(event["kind"]),
        "--materiality",
        str(event["materiality"]),
        "--direction",
        str(event["direction"]),
        "--one-liner",
        str(event["one_liner"]),
        "--dedup-key",
        str(event["dedup_key"]),
    ]
    for flag, values in {
        "--urls": event.get("urls"),
        "--themes": event.get("themes"),
        "--instruments": event.get("instruments"),
        "--touched": event.get("dashboard_files_touched"),
    }.items():
        if values:
            command.extend([flag, ",".join(str(value) for value in values)])
    for flag, value in {
        "--playbook": event.get("playbook_trigger"),
        "--catalyst-ref": event.get("catalyst_ref"),
        "--date": event.get("catalyst_date"),
        "--type": event.get("catalyst_type"),
    }.items():
        if value:
            command.extend([flag, str(value)])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"spine signal append timed out after {timeout_seconds}s") from exc
    except OSError as exc:
        raise RuntimeError("could not execute spine signal append") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip().splitlines()[-1][:300]
        raise RuntimeError(f"spine signal append failed: {detail}")


def emit_signals(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    fund_context: str | None = None,
    append_event: Callable[[dict[str, Any]], None] = append_signal_event,
    registry_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Append eligible events and mark each tweet only after spine accepts it."""
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(hours=24)
    cursor = conn.execute(
        """
        SELECT * FROM tweets
        WHERE signal_emitted_at IS NULL
          AND processed_at >= ?
          AND (
            relevance_score >= 7
            OR surprise = 2
            OR playbook_trigger IS NOT NULL
            OR catalyst_status = 'resolved'
          )
        ORDER BY processed_at, id
        """,
        (cutoff.isoformat(),),
    )
    if fund_context is None:
        fund_context, _ = load_fund_context()

    emitted = []
    effective_registry_dir = registry_dir or REGISTRY_DIR
    for row in cursor.fetchall():
        event = build_signal_event(row, fund_context=fund_context, registry_dir=effective_registry_dir)
        append_event(event)
        marked_at = current.isoformat()
        conn.execute("UPDATE tweets SET signal_emitted_at = ? WHERE id = ?", (marked_at, row["id"]))
        conn.commit()
        emitted.append(event)
    return emitted
