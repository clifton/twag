"""LLM usage cost tracking and queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import sqlite3


def log_llm_usage(
    conn: sqlite3.Connection,
    events: list[dict[str, Any]],
) -> int:
    """Insert usage events into the llm_usage table. Returns rows inserted."""
    if not events:
        return 0
    conn.executemany(
        """
        INSERT INTO llm_usage (timestamp, component, provider, model, input_tokens, output_tokens, estimated_cost_usd)
        VALUES (:timestamp, :component, :provider, :model, :input_tokens, :output_tokens, :estimated_cost_usd)
        """,
        events,
    )
    conn.commit()
    return len(events)


def get_cost_summary(
    conn: sqlite3.Connection,
    days: int | None = None,
) -> list[dict[str, Any]]:
    """Get cost summary grouped by component and model."""
    where = ""
    params: tuple = ()
    if days is not None:
        where = "WHERE timestamp >= datetime('now', ?)"
        params = (f"-{days} days",)
    cursor = conn.execute(
        f"""
        SELECT
            component,
            provider,
            model,
            COUNT(*) as calls,
            SUM(input_tokens) as total_input_tokens,
            SUM(output_tokens) as total_output_tokens,
            SUM(estimated_cost_usd) as total_cost_usd
        FROM llm_usage
        {where}
        GROUP BY component, provider, model
        ORDER BY total_cost_usd DESC
        """,
        params,
    )
    return [dict(row) for row in cursor.fetchall()]


def get_cost_by_component(
    conn: sqlite3.Connection,
    days: int | None = None,
) -> list[dict[str, Any]]:
    """Get cost totals grouped by component."""
    where = ""
    params: tuple = ()
    if days is not None:
        where = "WHERE timestamp >= datetime('now', ?)"
        params = (f"-{days} days",)
    cursor = conn.execute(
        f"""
        SELECT
            component,
            COUNT(*) as calls,
            SUM(input_tokens) as total_input_tokens,
            SUM(output_tokens) as total_output_tokens,
            SUM(estimated_cost_usd) as total_cost_usd
        FROM llm_usage
        {where}
        GROUP BY component
        ORDER BY total_cost_usd DESC
        """,
        params,
    )
    return [dict(row) for row in cursor.fetchall()]


def get_cost_by_date(
    conn: sqlite3.Connection,
    days: int | None = None,
) -> list[dict[str, Any]]:
    """Get daily cost totals."""
    where = ""
    params: tuple = ()
    if days is not None:
        where = "WHERE timestamp >= datetime('now', ?)"
        params = (f"-{days} days",)
    cursor = conn.execute(
        f"""
        SELECT
            DATE(timestamp) as date,
            COUNT(*) as calls,
            SUM(input_tokens) as total_input_tokens,
            SUM(output_tokens) as total_output_tokens,
            SUM(estimated_cost_usd) as total_cost_usd
        FROM llm_usage
        {where}
        GROUP BY DATE(timestamp)
        ORDER BY date DESC
        """,
        params,
    )
    return [dict(row) for row in cursor.fetchall()]


def get_total_cost(
    conn: sqlite3.Connection,
    days: int | None = None,
) -> float:
    """Get total estimated cost in USD."""
    where = ""
    params: tuple = ()
    if days is not None:
        where = "WHERE timestamp >= datetime('now', ?)"
        params = (f"-{days} days",)
    cursor = conn.execute(
        f"SELECT COALESCE(SUM(estimated_cost_usd), 0.0) FROM llm_usage {where}",
        params,
    )
    return float(cursor.fetchone()[0])
