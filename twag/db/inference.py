"""Persistent LLM inference usage logging and cost summaries."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

from .connection import commit_with_retry, get_connection

log = logging.getLogger(__name__)

LLM_USAGE_SQL = """
CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    called_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    component TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    max_tokens INTEGER,
    latency_seconds REAL,
    success INTEGER NOT NULL DEFAULT 1,
    error_type TEXT,
    error_message TEXT,
    estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
    input_cost_per_million REAL,
    output_cost_per_million REAL,
    cached_input_cost_per_million REAL,
    prompt_chars INTEGER,
    response_chars INTEGER,
    is_vision INTEGER NOT NULL DEFAULT 0,
    attempt_status TEXT NOT NULL DEFAULT 'completed',
    completed_at TEXT,
    status_id TEXT,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_called_at ON llm_usage(called_at);
CREATE INDEX IF NOT EXISTS idx_llm_usage_component ON llm_usage(component, called_at);
CREATE INDEX IF NOT EXISTS idx_llm_usage_provider_model ON llm_usage(provider, model, called_at);
"""

_LLM_USAGE_COLUMNS: dict[str, str] = {
    "reasoning_tokens": "INTEGER NOT NULL DEFAULT 0",
    "cached_input_tokens": "INTEGER NOT NULL DEFAULT 0",
    "total_tokens": "INTEGER NOT NULL DEFAULT 0",
    "max_tokens": "INTEGER",
    "latency_seconds": "REAL",
    "success": "INTEGER NOT NULL DEFAULT 1",
    "error_type": "TEXT",
    "error_message": "TEXT",
    "input_cost_per_million": "REAL",
    "output_cost_per_million": "REAL",
    "cached_input_cost_per_million": "REAL",
    "prompt_chars": "INTEGER",
    "response_chars": "INTEGER",
    "is_vision": "INTEGER NOT NULL DEFAULT 0",
    "attempt_status": "TEXT NOT NULL DEFAULT 'completed'",
    "completed_at": "TEXT",
    "status_id": "TEXT",
    "metadata_json": "TEXT",
}


@dataclass(frozen=True)
class ModelPrice:
    """Per-1M-token model prices in USD."""

    input_per_million: float
    output_per_million: float
    cached_input_per_million: float | None = None


# Standard-tier estimates from provider pricing pages. Keep this table small and
# explicit; unknown models still log tokens with cost = 0.
MODEL_PRICES: dict[tuple[str, str], ModelPrice] = {
    ("deepseek", "deepseek-v4-flash"): ModelPrice(0.14, 0.28, 0.0028),
    ("deepseek", "deepseek-v4-pro"): ModelPrice(0.435, 0.87, 0.003625),
    ("gemini", "gemini-2.5-flash"): ModelPrice(0.30, 2.50, 0.03),
    ("gemini", "gemini-2.5-flash-lite"): ModelPrice(0.10, 0.40, 0.01),
    ("gemini", "gemini-2.5-flash-lite-preview-09-2025"): ModelPrice(0.10, 0.40, 0.01),
    ("gemini", "gemini-2.5-pro"): ModelPrice(1.25, 10.00, 0.125),
    ("gemini", "gemini-3-flash-preview"): ModelPrice(0.50, 3.00, 0.05),
    ("gemini", "gemini-3.1-flash-lite-preview"): ModelPrice(0.25, 1.50, 0.025),
    ("gemini", "gemini-3.1-pro-preview"): ModelPrice(2.00, 12.00, 0.20),
}


def _normal_key(provider: str, model: str) -> tuple[str, str]:
    return provider.strip().lower(), model.strip().lower()


def get_model_price(provider: str, model: str) -> ModelPrice | None:
    """Return configured model pricing, if known."""
    provider_key, model_key = _normal_key(provider, model)
    if (provider_key, model_key) in MODEL_PRICES:
        return MODEL_PRICES[(provider_key, model_key)]

    # Accept dated/aliased suffixes by matching the longest configured prefix.
    matches = [
        (known_model, price)
        for (known_provider, known_model), price in MODEL_PRICES.items()
        if known_provider == provider_key and model_key.startswith(known_model)
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda item: len(item[0]), reverse=True)[0][1]


def estimate_cost_usd(
    provider: str,
    model: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    reasoning_tokens: int = 0,
    cached_input_tokens: int = 0,
) -> tuple[float, ModelPrice | None]:
    """Estimate provider cost for one call using known per-1M-token rates."""
    price = get_model_price(provider, model)
    if price is None:
        return 0.0, None

    cached = max(0, cached_input_tokens)
    uncached_input = max(0, input_tokens - cached)
    cached_rate = (
        price.cached_input_per_million if price.cached_input_per_million is not None else price.input_per_million
    )

    # Gemini reports thinking tokens separately, while its output price includes
    # thinking. DeepSeek/OpenAI-style completion tokens already include billable
    # completion usage, so only Gemini adds reasoning_tokens here.
    billable_output = output_tokens + (reasoning_tokens if provider.strip().lower() == "gemini" else 0)

    cost = (
        (uncached_input / 1_000_000) * price.input_per_million
        + (cached / 1_000_000) * cached_rate
        + (max(0, billable_output) / 1_000_000) * price.output_per_million
    )
    return cost, price


def ensure_llm_usage_table(conn: sqlite3.Connection) -> None:
    """Create or migrate the LLM usage table."""
    conn.executescript(LLM_USAGE_SQL)

    cursor = conn.execute("PRAGMA table_info(llm_usage)")
    columns = {row[1] for row in cursor.fetchall()}
    for column, column_type in _LLM_USAGE_COLUMNS.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE llm_usage ADD COLUMN {column} {column_type}")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_called_at ON llm_usage(called_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_component ON llm_usage(component, called_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_provider_model ON llm_usage(provider, model, called_at)")


def begin_llm_usage_attempt(
    *,
    component: str,
    provider: str,
    model: str,
    max_tokens: int | None = None,
    prompt_chars: int | None = None,
    is_vision: bool = False,
    status_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: Path | None = None,
) -> int | None:
    """Persist a provider attempt before the network request is made."""
    try:
        metadata_json = json.dumps(metadata, sort_keys=True) if metadata else None
        with get_connection(db_path) as conn:
            ensure_llm_usage_table(conn)
            cursor = conn.execute(
                """
                INSERT INTO llm_usage (
                    called_at, component, provider, model,
                    max_tokens, success, estimated_cost_usd, prompt_chars,
                    is_vision, status_id, metadata_json, attempt_status
                )
                VALUES (?, ?, ?, ?, ?, 0, 0.0, ?, ?, ?, ?, 'started')
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    component,
                    provider,
                    model,
                    max_tokens,
                    prompt_chars,
                    1 if is_vision else 0,
                    status_id,
                    metadata_json,
                ),
            )
            commit_with_retry(conn)
            return cursor.lastrowid
    except Exception:
        log.debug("Failed to begin LLM usage attempt", exc_info=True)
        return None


def complete_llm_usage_attempt(
    attempt_id: int | None,
    *,
    component: str,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    reasoning_tokens: int = 0,
    cached_input_tokens: int = 0,
    total_tokens: int = 0,
    max_tokens: int | None = None,
    latency_seconds: float | None = None,
    success: bool = True,
    error_type: str | None = None,
    error_message: str | None = None,
    prompt_chars: int | None = None,
    response_chars: int | None = None,
    is_vision: bool = False,
    status_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: Path | None = None,
) -> None:
    """Update a started provider attempt, falling back to an insert if needed."""
    if attempt_id is None:
        record_llm_usage(
            component=component,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens,
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            latency_seconds=latency_seconds,
            success=success,
            error_type=error_type,
            error_message=error_message,
            prompt_chars=prompt_chars,
            response_chars=response_chars,
            is_vision=is_vision,
            status_id=status_id,
            metadata=metadata,
            db_path=db_path,
        )
        return

    try:
        estimated_cost, price = estimate_cost_usd(
            provider,
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens,
        )
        metadata_json = json.dumps(metadata, sort_keys=True) if metadata else None
        with get_connection(db_path) as conn:
            ensure_llm_usage_table(conn)
            cursor = conn.execute(
                """
                UPDATE llm_usage
                SET
                    component = ?,
                    provider = ?,
                    model = ?,
                    input_tokens = ?,
                    output_tokens = ?,
                    reasoning_tokens = ?,
                    cached_input_tokens = ?,
                    total_tokens = ?,
                    max_tokens = ?,
                    latency_seconds = ?,
                    success = ?,
                    error_type = ?,
                    error_message = ?,
                    estimated_cost_usd = ?,
                    input_cost_per_million = ?,
                    output_cost_per_million = ?,
                    cached_input_cost_per_million = ?,
                    prompt_chars = COALESCE(?, prompt_chars),
                    response_chars = ?,
                    is_vision = ?,
                    status_id = COALESCE(?, status_id),
                    metadata_json = ?,
                    attempt_status = ?,
                    completed_at = ?
                WHERE id = ?
                """,
                (
                    component,
                    provider,
                    model,
                    int(input_tokens or 0),
                    int(output_tokens or 0),
                    int(reasoning_tokens or 0),
                    int(cached_input_tokens or 0),
                    int(total_tokens or 0),
                    max_tokens,
                    latency_seconds,
                    1 if success else 0,
                    error_type,
                    (error_message or "")[:500] if error_message else None,
                    estimated_cost,
                    price.input_per_million if price else None,
                    price.output_per_million if price else None,
                    price.cached_input_per_million if price else None,
                    prompt_chars,
                    response_chars,
                    1 if is_vision else 0,
                    status_id,
                    metadata_json,
                    "success" if success else "error",
                    datetime.now(timezone.utc).isoformat(),
                    attempt_id,
                ),
            )
            if cursor.rowcount == 0:
                raise RuntimeError(f"LLM usage attempt {attempt_id} was not found")
            commit_with_retry(conn)
    except Exception:
        log.debug("Failed to complete LLM usage attempt", exc_info=True)
        record_llm_usage(
            component=component,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens,
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            latency_seconds=latency_seconds,
            success=success,
            error_type=error_type,
            error_message=error_message,
            prompt_chars=prompt_chars,
            response_chars=response_chars,
            is_vision=is_vision,
            status_id=status_id,
            metadata=metadata,
            db_path=db_path,
        )


def record_llm_usage(
    *,
    component: str,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    reasoning_tokens: int = 0,
    cached_input_tokens: int = 0,
    total_tokens: int = 0,
    max_tokens: int | None = None,
    latency_seconds: float | None = None,
    success: bool = True,
    error_type: str | None = None,
    error_message: str | None = None,
    prompt_chars: int | None = None,
    response_chars: int | None = None,
    is_vision: bool = False,
    status_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: Path | None = None,
) -> None:
    """Persist a single LLM call attempt.

    Logging should never break the scoring path; failures are debug-logged and
    swallowed by design.
    """
    try:
        estimated_cost, price = estimate_cost_usd(
            provider,
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens,
        )
        metadata_json = json.dumps(metadata, sort_keys=True) if metadata else None
        with get_connection(db_path) as conn:
            ensure_llm_usage_table(conn)
            conn.execute(
                """
                INSERT INTO llm_usage (
                    called_at, component, provider, model,
                    input_tokens, output_tokens, reasoning_tokens, cached_input_tokens, total_tokens,
                    max_tokens, latency_seconds, success, error_type, error_message,
                    estimated_cost_usd, input_cost_per_million, output_cost_per_million,
                    cached_input_cost_per_million, prompt_chars, response_chars, is_vision,
                    attempt_status, completed_at, status_id, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    component,
                    provider,
                    model,
                    int(input_tokens or 0),
                    int(output_tokens or 0),
                    int(reasoning_tokens or 0),
                    int(cached_input_tokens or 0),
                    int(total_tokens or 0),
                    max_tokens,
                    latency_seconds,
                    1 if success else 0,
                    error_type,
                    (error_message or "")[:500] if error_message else None,
                    estimated_cost,
                    price.input_per_million if price else None,
                    price.output_per_million if price else None,
                    price.cached_input_per_million if price else None,
                    prompt_chars,
                    response_chars,
                    1 if is_vision else 0,
                    "success" if success else "error",
                    datetime.now(timezone.utc).isoformat(),
                    status_id,
                    metadata_json,
                ),
            )
            commit_with_retry(conn)
    except Exception:
        log.debug("Failed to record LLM usage", exc_info=True)


def since_to_iso(days: int | None) -> str | None:
    """Return UTC ISO cutoff for a day window."""
    if days is None:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, days))
    return cutoff.isoformat()


def summarize_llm_usage(
    *,
    days: int | None = 30,
    provider: str | None = None,
    model: str | None = None,
    component: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Summarize usage by component/provider/model."""
    where = []
    params: list[Any] = []
    since = since_to_iso(days)
    if since:
        where.append("called_at >= ?")
        params.append(since)
    if provider:
        where.append("provider = ?")
        params.append(provider)
    if model:
        where.append("model = ?")
        params.append(model)
    if component:
        where.append("component = ?")
        params.append(component)

    sql_where = f"WHERE {' AND '.join(where)}" if where else ""
    with get_connection(db_path, readonly=True) as conn:
        rows = conn.execute(
            f"""
            SELECT
                component,
                provider,
                model,
                COUNT(*) AS calls,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successes,
                SUM(CASE WHEN success = 0 AND COALESCE(attempt_status, 'completed') != 'started' THEN 1 ELSE 0 END) AS failures,
                SUM(CASE WHEN COALESCE(attempt_status, 'completed') = 'started' THEN 1 ELSE 0 END) AS incomplete_attempts,
                SUM(input_tokens) AS input_tokens,
                SUM(output_tokens) AS output_tokens,
                SUM(reasoning_tokens) AS reasoning_tokens,
                SUM(cached_input_tokens) AS cached_input_tokens,
                SUM(total_tokens) AS total_tokens,
                SUM(estimated_cost_usd) AS stored_estimated_cost_usd,
                AVG(latency_seconds) AS avg_latency_seconds
            FROM llm_usage
            {sql_where}
            GROUP BY component, provider, model
            ORDER BY stored_estimated_cost_usd DESC, calls DESC
            """,
            tuple(params),
        ).fetchall()

    summaries: list[dict[str, Any]] = []
    for row in rows:
        reestimated_cost, _ = estimate_cost_usd(
            row["provider"],
            row["model"],
            input_tokens=int(row["input_tokens"] or 0),
            output_tokens=int(row["output_tokens"] or 0),
            reasoning_tokens=int(row["reasoning_tokens"] or 0),
            cached_input_tokens=int(row["cached_input_tokens"] or 0),
        )
        item = dict(row)
        item["reestimated_cost_usd"] = reestimated_cost
        summaries.append(item)
    summaries.sort(key=lambda item: (item["reestimated_cost_usd"], item["calls"]), reverse=True)
    return summaries
