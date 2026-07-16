"""Tests for persistent inference usage logging."""

from click.testing import CliRunner

from twag.cli import cli
from twag.db import get_connection, init_db
from twag.db.inference import estimate_cost_usd, record_llm_usage, summarize_llm_usage


def test_estimate_gemini_cost_includes_reasoning_tokens() -> None:
    cost, price = estimate_cost_usd(
        "gemini",
        "gemini-3-flash-preview",
        input_tokens=1_000_000,
        output_tokens=100_000,
        reasoning_tokens=100_000,
        cached_input_tokens=100_000,
    )

    assert price is not None
    assert round(cost, 4) == 1.055


def test_record_and_summarize_llm_usage(tmp_path) -> None:
    db_path = tmp_path / "usage.db"
    init_db(db_path)

    record_llm_usage(
        component="triage",
        provider="gemini",
        model="gemini-3-flash-preview",
        input_tokens=1000,
        output_tokens=200,
        reasoning_tokens=50,
        total_tokens=1250,
        latency_seconds=1.5,
        prompt_chars=4000,
        response_chars=600,
        db_path=db_path,
    )

    rows = summarize_llm_usage(days=None, db_path=db_path)

    assert len(rows) == 1
    row = rows[0]
    assert row["component"] == "triage"
    assert row["provider"] == "gemini"
    assert row["calls"] == 1
    assert row["input_tokens"] == 1000
    assert row["output_tokens"] == 200
    assert row["reasoning_tokens"] == 50
    assert row["reestimated_cost_usd"] > 0


def test_usage_command_shows_only_logged_rows(monkeypatch) -> None:
    import twag.cli.inference as inference_mod

    monkeypatch.setattr(inference_mod, "init_db", lambda: None)
    monkeypatch.setattr(
        inference_mod,
        "summarize_llm_usage",
        lambda **_kwargs: [
            {
                "component": "triage",
                "provider": "gemini",
                "model": "gemini-3-flash-preview",
                "calls": 2,
                "failures": 0,
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "output_tokens": 20,
                "reasoning_tokens": 5,
                "reestimated_cost_usd": 0.001,
                "avg_latency_seconds": 1.23,
            },
        ],
    )

    result = CliRunner().invoke(cli, ["inference", "usage", "--days", "7"])

    assert result.exit_code == 0
    assert "LLM Inference Usage - last 7d" in result.output
    assert "gemini-3-flash-preview" in result.output
    assert "$0.0010" in result.output


def test_existing_llm_usage_table_is_migrated(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                component TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost_usd REAL NOT NULL DEFAULT 0.0
            )
            """,
        )
        conn.execute(
            """
            INSERT INTO llm_usage (component, provider, model, input_tokens, output_tokens)
            VALUES ('triage', 'gemini', 'gemini-3-flash-preview', 10, 5)
            """,
        )
        conn.commit()

    init_db(db_path)

    with get_connection(db_path, readonly=True) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(llm_usage)").fetchall()}
        count = conn.execute("SELECT COUNT(*) AS count FROM llm_usage").fetchone()["count"]

    assert "latency_seconds" in columns
    assert "cached_input_tokens" in columns
    assert count == 1
