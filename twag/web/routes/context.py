"""Context command management API routes."""

import asyncio
import re
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ...db import (
    delete_context_command,
    get_all_context_commands,
    get_connection,
    get_context_command,
    get_tweet_by_id,
    toggle_context_command,
    upsert_context_command,
)
from ...media import build_media_context, parse_media_items
from ...processor import ensure_media_analysis

router = APIRouter(tags=["context"])


class ContextCommandCreate(BaseModel):
    """Request body for creating/updating a context command."""

    name: str
    command_template: str
    description: str | None = None
    enabled: bool = True


class TestCommandRequest(BaseModel):
    """Request body for testing a context command."""

    tweet_id: str


@router.get("/context-commands")
async def list_context_commands(
    request: Request,
    enabled_only: bool = False,
) -> dict[str, Any]:
    """Get all context commands."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        commands = get_all_context_commands(conn, enabled_only)

    return {
        "commands": [
            {
                "id": cmd.id,
                "name": cmd.name,
                "command_template": cmd.command_template,
                "description": cmd.description,
                "enabled": cmd.enabled,
                "created_at": cmd.created_at.isoformat() if cmd.created_at else None,
            }
            for cmd in commands
        ]
    }


@router.post("/context-commands")
async def create_context_command(
    request: Request,
    command: ContextCommandCreate,
) -> dict[str, Any]:
    """Create a new context command."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        cmd_id = upsert_context_command(
            conn,
            command.name,
            command.command_template,
            command.description,
            command.enabled,
        )
        conn.commit()

    return {
        "id": cmd_id,
        "name": command.name,
        "message": "Context command created",
    }


@router.get("/context-commands/{name}")
async def get_context_command_by_name(
    request: Request,
    name: str,
) -> dict[str, Any]:
    """Get a specific context command."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        cmd = get_context_command(conn, name)

    if not cmd:
        return {"error": "Context command not found"}

    return {
        "id": cmd.id,
        "name": cmd.name,
        "command_template": cmd.command_template,
        "description": cmd.description,
        "enabled": cmd.enabled,
        "created_at": cmd.created_at.isoformat() if cmd.created_at else None,
    }


@router.put("/context-commands/{name}")
async def update_context_command(
    request: Request,
    name: str,
    command: ContextCommandCreate,
) -> dict[str, Any]:
    """Update a context command."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        cmd_id = upsert_context_command(
            conn,
            name,
            command.command_template,
            command.description,
            command.enabled,
        )
        conn.commit()

    return {
        "id": cmd_id,
        "name": name,
        "message": "Context command updated",
    }


@router.delete("/context-commands/{name}")
async def remove_context_command(
    request: Request,
    name: str,
) -> dict[str, Any]:
    """Delete a context command."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        deleted = delete_context_command(conn, name)
        conn.commit()

    if deleted:
        return {"message": f"Context command '{name}' deleted"}
    return {"error": "Context command not found"}


@router.post("/context-commands/{name}/toggle")
async def toggle_command(
    request: Request,
    name: str,
    enabled: bool,
) -> dict[str, Any]:
    """Enable or disable a context command."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        found = toggle_context_command(conn, name, enabled)
        conn.commit()

    if found:
        status = "enabled" if enabled else "disabled"
        return {"message": f"Context command '{name}' {status}"}
    return {"error": "Context command not found"}


def _substitute_variables(template: str, variables: dict[str, str]) -> str:
    """Substitute {var} placeholders in template with values."""
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{key}}}", value)
    return result


def _extract_tweet_variables(tweet_row) -> dict[str, str]:
    """Extract variables from a tweet for command substitution."""
    import json
    from datetime import datetime

    variables = {
        "tweet_id": tweet_row["id"],
        "author": tweet_row["author_handle"],
    }

    # Parse created_at
    if tweet_row["created_at"]:
        try:
            dt = datetime.fromisoformat(tweet_row["created_at"].replace("Z", "+00:00"))
            variables["tweet_date"] = dt.strftime("%Y-%m-%d")
            variables["tweet_datetime"] = dt.isoformat()
        except ValueError:
            variables["tweet_date"] = ""
            variables["tweet_datetime"] = ""
    else:
        variables["tweet_date"] = ""
        variables["tweet_datetime"] = ""

    # Extract first ticker
    if tweet_row["tickers"]:
        try:
            tickers = json.loads(tweet_row["tickers"])
            variables["ticker"] = tickers[0] if tickers else ""
            variables["tickers"] = ",".join(tickers)
        except json.JSONDecodeError:
            tickers = [t.strip() for t in tweet_row["tickers"].split(",") if t.strip()]
            variables["ticker"] = tickers[0] if tickers else ""
            variables["tickers"] = ",".join(tickers)
    else:
        variables["ticker"] = ""
        variables["tickers"] = ""

    return variables


async def _run_command(command: str, timeout: float = 30.0) -> tuple[str, str, int]:
    """Run a shell command and return (stdout, stderr, returncode)."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
        return (
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
            proc.returncode or 0,
        )
    except asyncio.TimeoutError:
        return "", "Command timed out", -1
    except Exception as e:
        return "", str(e), -1


@router.post("/context-commands/{name}/test")
async def test_context_command(
    request: Request,
    name: str,
    test_req: TestCommandRequest,
) -> dict[str, Any]:
    """
    Test a context command with a sample tweet.

    Substitutes tweet variables and runs the command.
    """
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        cmd = get_context_command(conn, name)
        if not cmd:
            return {"error": "Context command not found"}

        tweet = get_tweet_by_id(conn, test_req.tweet_id)
        if not tweet:
            return {"error": "Tweet not found"}

    # Extract variables and substitute
    variables = _extract_tweet_variables(tweet)
    final_command = _substitute_variables(cmd.command_template, variables)

    # Check for unsubstituted variables
    unsubstituted = re.findall(r"\{(\w+)\}", final_command)
    if unsubstituted:
        return {
            "error": f"Unsubstituted variables: {unsubstituted}",
            "available_variables": list(variables.keys()),
            "command_template": cmd.command_template,
            "final_command": final_command,
        }

    # Run the command
    stdout, stderr, returncode = await _run_command(final_command)

    return {
        "command_name": name,
        "command_template": cmd.command_template,
        "final_command": final_command,
        "variables_used": variables,
        "stdout": stdout,
        "stderr": stderr,
        "returncode": returncode,
        "success": returncode == 0,
    }


@router.post("/analyze/{tweet_id}")
async def analyze_tweet_with_context(
    request: Request,
    tweet_id: str,
) -> dict[str, Any]:
    """
    Deep analyze a tweet with context injection from enabled commands.

    Runs all enabled context commands, injects their output into the
    analysis prompt, and returns enriched analysis.
    """
    import json

    from ...scorer import _call_llm

    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        tweet = get_tweet_by_id(conn, tweet_id)
        if not tweet:
            return {"error": "Tweet not found"}

        commands = get_all_context_commands(conn, enabled_only=True)
        media_items = ensure_media_analysis(conn, tweet)
        if media_items:
            conn.commit()
        else:
            media_items = parse_media_items(tweet["media_items"])

    # Extract variables
    variables = _extract_tweet_variables(tweet)

    # Run all enabled context commands
    context_results = {}
    for cmd in commands:
        final_command = _substitute_variables(cmd.command_template, variables)

        # Skip if has unsubstituted variables
        if re.findall(r"\{(\w+)\}", final_command):
            continue

        stdout, stderr, returncode = await _run_command(final_command, timeout=15.0)
        if returncode == 0 and stdout.strip():
            context_results[cmd.name] = stdout.strip()

    # Build analysis prompt with injected context
    context_section = ""
    if context_results:
        context_parts = []
        for name, output in context_results.items():
            context_parts.append(f"### {name}\n{output}")
        context_section = "\n\n".join(context_parts)

    # Parse existing data
    categories = []
    if tweet["category"]:
        try:
            categories = json.loads(tweet["category"])
        except json.JSONDecodeError:
            categories = [tweet["category"]]

    media_context = build_media_context(media_items) if media_items else ""

    analysis_prompt = f"""Analyze this tweet in depth with the additional context provided.

Tweet by @{tweet["author_handle"]}:
{tweet["content"]}

Current scoring:
- Relevance score: {tweet["relevance_score"]}
- Categories: {categories}
- Signal tier: {tweet["signal_tier"]}
- Summary: {tweet["summary"]}

{"## Media Context" if media_context else ""}
{media_context}

{"## Additional Context" if context_section else ""}
{context_section}

Provide a comprehensive analysis including:
1. How does the additional context change the interpretation?
2. Is the current scoring accurate given this context?
3. What specific actions or insights does this suggest?
4. Any risks or opportunities not captured in the original scoring?

Return your analysis in a structured format."""

    try:
        from ...config import load_config

        config = load_config()
        model = config["llm"]["enrichment_model"]
        provider = config["llm"].get("enrichment_provider", "anthropic")

        analysis = _call_llm(provider, model, analysis_prompt, max_tokens=2048)

        return {
            "tweet_id": tweet_id,
            "author": tweet["author_handle"],
            "content": tweet["content"][:500],
            "original_score": tweet["relevance_score"],
            "original_tier": tweet["signal_tier"],
            "context_commands_run": list(context_results.keys()),
            "context_data": context_results,
            "analysis": analysis,
        }

    except Exception as e:
        return {"error": f"Analysis failed: {e!s}"}
