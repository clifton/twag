"""Prompt CRUD operations for editable LLM prompts."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class Prompt:
    """An editable LLM prompt template."""

    id: int
    name: str
    template: str
    version: int
    updated_at: datetime | None
    updated_by: str | None


# Default prompts to seed from scorer.py
DEFAULT_PROMPTS = {
    "triage": """You are a financial markets triage agent. Score this tweet 0-10 for relevance to macro/investing.

Categories (assign 1-3 that apply): fed_policy, inflation, job_market, macro_data, earnings, equities, rates_fx, credit, banks, consumer_spending, capex, commodities, energy, metals_mining, geopolitical, sanctions, tech_business, ai_advancement, crypto, noise

Tweet: {tweet_text}
Author: @{handle}

Return JSON only:
{{"score": 7, "categories": ["fed_policy", "rates_fx"], "summary": "One-liner summary", "tickers": ["TLT", "GLD"]}}""",
    "batch_triage": """You are a financial markets triage agent. Score these tweets 0-10 for relevance to macro/investing.

Categories (assign 1-3 that apply): fed_policy, inflation, job_market, macro_data, earnings, equities, rates_fx, credit, banks, consumer_spending, capex, commodities, energy, metals_mining, geopolitical, sanctions, tech_business, ai_advancement, crypto, noise

Tweets:
{tweets}

Return a JSON array with one object per tweet, in order:
[{{"id": "tweet_id", "score": 7, "categories": ["fed_policy", "rates_fx"], "summary": "One-liner", "tickers": ["TLT"]}}]""",
    "enrichment": """You are a financial analyst. Analyze this tweet for actionable insights.

Tweet: {tweet_text}
Author: @{handle} ({author_category})
Quoted: {quoted_tweet}
Linked article: {article_summary}
Media context: {image_description}

Provide:
1. Signal tier: high_signal | market_relevant | news | noise
2. Key insight (1-2 sentences)
3. Investment implications with specific tickers
4. Any emerging narratives this connects to

Return JSON:
{{"signal_tier": "high_signal", "insight": "...", "implications": "...", "narratives": ["Fed pivot"], "tickers": ["TLT"]}}""",
    "summarize": """Summarize this tweet concisely while preserving all key market-relevant information, data points, and actionable insights. Keep ticker symbols and specific numbers.

Tweet by @{handle}:
{tweet_text}

Provide a summary in 2-4 sentences (under 400 characters). Return only the summary text, no JSON.""",
    "vision": """Analyze this image from a financial Twitter post.

Determine if it is a chart, a document/screen with coherent prose, or a meme/photo/other.

Return JSON:
{
  "kind": "chart|document|screenshot|meme|photo|other",
  "short_description": "very short description (3-8 words)",
  "prose_text": "FULL text if it's coherent prose; otherwise empty string",
  "prose_summary": "short summary if prose; otherwise empty string",
  "chart": {
    "type": "line|bar|candlestick|heatmap|table|other",
    "description": "what data is shown",
    "insight": "key visual insight",
    "implication": "investment implication",
    "tickers": ["AAPL"]
  }
}

Rules:
- If NOT a chart, set chart fields to empty strings and [].
- If there is not coherent prose, set prose_text to "".
- If prose_text is provided, preserve paragraphs and wording as written.
- short_description should be very short and neutral.
""",
}


def seed_prompts(conn: sqlite3.Connection) -> int:
    """Seed default prompts if they don't exist. Returns count of seeded prompts."""
    count = 0
    for name, template in DEFAULT_PROMPTS.items():
        cursor = conn.execute("SELECT 1 FROM prompts WHERE name = ?", (name,))
        if not cursor.fetchone():
            conn.execute(
                """
                INSERT INTO prompts (name, template, version, updated_at, updated_by)
                VALUES (?, ?, 1, ?, 'seed')
                """,
                (name, template, datetime.now(timezone.utc).isoformat()),
            )
            count += 1
    return count


def get_prompt(conn: sqlite3.Connection, name: str) -> Prompt | None:
    """Get a prompt by name."""
    cursor = conn.execute(
        "SELECT * FROM prompts WHERE name = ?",
        (name,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    updated_at = None
    if row["updated_at"]:
        try:
            updated_at = datetime.fromisoformat(row["updated_at"])
        except ValueError:
            pass

    return Prompt(
        id=row["id"],
        name=row["name"],
        template=row["template"],
        version=row["version"],
        updated_at=updated_at,
        updated_by=row["updated_by"],
    )


def get_all_prompts(conn: sqlite3.Connection) -> list[Prompt]:
    """Get all prompts."""
    cursor = conn.execute("SELECT * FROM prompts ORDER BY name")
    results = []
    for row in cursor.fetchall():
        updated_at = None
        if row["updated_at"]:
            try:
                updated_at = datetime.fromisoformat(row["updated_at"])
            except ValueError:
                pass
        results.append(
            Prompt(
                id=row["id"],
                name=row["name"],
                template=row["template"],
                version=row["version"],
                updated_at=updated_at,
                updated_by=row["updated_by"],
            )
        )
    return results


def upsert_prompt(
    conn: sqlite3.Connection,
    name: str,
    template: str,
    updated_by: str = "user",
) -> int:
    """Insert or update a prompt. Returns new version number."""
    # Get current version if exists
    cursor = conn.execute("SELECT version, template FROM prompts WHERE name = ?", (name,))
    row = cursor.fetchone()

    if row:
        old_version = row["version"]
        old_template = row["template"]

        # Save to history before updating
        conn.execute(
            """
            INSERT INTO prompt_history (prompt_name, template, version)
            VALUES (?, ?, ?)
            """,
            (name, old_template, old_version),
        )

        new_version = old_version + 1
        conn.execute(
            """
            UPDATE prompts SET
                template = ?,
                version = ?,
                updated_at = ?,
                updated_by = ?
            WHERE name = ?
            """,
            (template, new_version, datetime.now(timezone.utc).isoformat(), updated_by, name),
        )
        return new_version

    conn.execute(
        """
        INSERT INTO prompts (name, template, version, updated_at, updated_by)
        VALUES (?, ?, 1, ?, ?)
        """,
        (name, template, datetime.now(timezone.utc).isoformat(), updated_by),
    )
    return 1


def get_prompt_history(conn: sqlite3.Connection, name: str, limit: int = 10) -> list[dict[str, Any]]:
    """Get version history for a prompt."""
    cursor = conn.execute(
        """
        SELECT * FROM prompt_history
        WHERE prompt_name = ?
        ORDER BY version DESC
        LIMIT ?
        """,
        (name, limit),
    )
    return [dict(row) for row in cursor.fetchall()]


def rollback_prompt(conn: sqlite3.Connection, name: str, to_version: int) -> bool:
    """Rollback a prompt to a specific version. Returns True if successful."""
    cursor = conn.execute(
        """
        SELECT template FROM prompt_history
        WHERE prompt_name = ? AND version = ?
        """,
        (name, to_version),
    )
    row = cursor.fetchone()
    if not row:
        return False

    upsert_prompt(conn, name, row["template"], updated_by="rollback")
    return True
