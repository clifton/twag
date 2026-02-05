"""Prompt management API routes."""

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ...db import (
    get_all_prompts,
    get_connection,
    get_prompt,
    get_prompt_history,
    get_reactions_with_tweets,
    rollback_prompt,
    upsert_prompt,
)

router = APIRouter(tags=["prompts"])


class PromptUpdate(BaseModel):
    """Request body for updating a prompt."""

    template: str
    updated_by: str = "user"


class TuneRequest(BaseModel):
    """Request body for LLM-assisted prompt tuning."""

    prompt_name: str
    reaction_limit: int = 50


@router.get("/prompts")
async def list_prompts(request: Request) -> dict[str, Any]:
    """Get all prompts."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        prompts = get_all_prompts(conn)

    return {
        "prompts": [
            {
                "id": p.id,
                "name": p.name,
                "template": p.template,
                "version": p.version,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "updated_by": p.updated_by,
            }
            for p in prompts
        ]
    }


@router.get("/prompts/{name}")
async def get_prompt_by_name(request: Request, name: str) -> dict[str, Any]:
    """Get a specific prompt by name."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        prompt = get_prompt(conn, name)

    if not prompt:
        return {"error": "Prompt not found"}

    return {
        "id": prompt.id,
        "name": prompt.name,
        "template": prompt.template,
        "version": prompt.version,
        "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
        "updated_by": prompt.updated_by,
    }


@router.put("/prompts/{name}")
async def update_prompt(
    request: Request,
    name: str,
    update: PromptUpdate,
) -> dict[str, Any]:
    """Update a prompt template."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        new_version = upsert_prompt(conn, name, update.template, update.updated_by)
        conn.commit()

    return {
        "name": name,
        "version": new_version,
        "message": "Prompt updated",
    }


@router.get("/prompts/{name}/history")
async def get_history(request: Request, name: str, limit: int = 10) -> dict[str, Any]:
    """Get version history for a prompt."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        history = get_prompt_history(conn, name, limit)

    return {
        "name": name,
        "history": history,
    }


@router.post("/prompts/{name}/rollback")
async def rollback_to_version(
    request: Request,
    name: str,
    version: int,
) -> dict[str, Any]:
    """Rollback a prompt to a specific version."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        success = rollback_prompt(conn, name, version)
        conn.commit()

    if success:
        return {"message": f"Rolled back {name} to version {version}"}
    return {"error": f"Version {version} not found for prompt {name}"}


@router.post("/prompts/tune")
async def tune_prompt(request: Request, tune_req: TuneRequest) -> dict[str, Any]:
    """
    LLM-assisted prompt tuning based on user reactions.

    Analyzes user feedback (reactions) to suggest prompt improvements.
    """
    import json

    from ...scorer import _call_llm

    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        # Get current prompt
        prompt = get_prompt(conn, tune_req.prompt_name)
        if not prompt:
            return {"error": f"Prompt '{tune_req.prompt_name}' not found"}

        # Get reactions with tweets
        high_importance = get_reactions_with_tweets(conn, ">>", tune_req.reaction_limit)
        should_be_higher = get_reactions_with_tweets(conn, ">", tune_req.reaction_limit)
        less_important = get_reactions_with_tweets(conn, "<", tune_req.reaction_limit)

    if not high_importance and not should_be_higher and not less_important:
        return {"error": "No reactions found. Add reactions to tweets first."}

    # Format reaction examples
    def format_examples(reactions: list) -> str:
        examples = []
        for reaction, tweet in reactions[:10]:  # Limit examples
            categories = []
            if tweet["category"]:
                try:
                    categories = json.loads(tweet["category"])
                except json.JSONDecodeError:
                    categories = [tweet["category"]]

            reason_text = f" (Reason: {reaction.reason})" if reaction.reason else ""
            examples.append(
                f"- Score: {tweet['relevance_score']}, Categories: {categories}, "
                f"Summary: {tweet['summary'][:100]}...{reason_text}"
            )
        return "\n".join(examples) if examples else "[none]"

    # Build tuning prompt
    tuning_prompt = f"""Analyze user feedback on tweet scoring and suggest improvements to the scoring prompt.

Current prompt:
```
{prompt.template}
```

User marked as HIGH IMPORTANCE (>>):
These tweets were scored too low - they should be top-tier:
{format_examples(high_importance)}

User marked as SHOULD BE HIGHER (>):
These tweets were underrated:
{format_examples(should_be_higher)}

User marked as LESS IMPORTANT (<):
These tweets were overrated:
{format_examples(less_important)}

Based on this feedback, suggest specific changes to improve the scoring prompt.
Consider:
1. Are certain categories being underweighted or overweighted?
2. Should the scoring criteria be adjusted?
3. Are there patterns in what users find important vs. what the current prompt prioritizes?

Return the complete updated prompt (not just the changes).
Format your response as:

ANALYSIS:
[Your analysis of the feedback patterns]

SUGGESTED PROMPT:
```
[The complete updated prompt]
```
"""

    try:
        # Use enrichment model for prompt tuning (more capable)
        from ...config import load_config

        config = load_config()
        model = config["llm"]["enrichment_model"]
        provider = config["llm"].get("enrichment_provider", "anthropic")

        response = _call_llm(provider, model, tuning_prompt, max_tokens=4096)

        # Parse response
        analysis = ""
        suggested_prompt = ""

        if "ANALYSIS:" in response:
            parts = response.split("SUGGESTED PROMPT:")
            if len(parts) == 2:
                analysis = parts[0].replace("ANALYSIS:", "").strip()
                suggested_prompt = parts[1].strip()
                # Remove code fences if present
                if suggested_prompt.startswith("```"):
                    lines = suggested_prompt.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    suggested_prompt = "\n".join(lines)
        else:
            analysis = response
            suggested_prompt = ""

        return {
            "prompt_name": tune_req.prompt_name,
            "current_version": prompt.version,
            "analysis": analysis,
            "suggested_prompt": suggested_prompt,
            "reactions_analyzed": {
                "high_importance": len(high_importance),
                "should_be_higher": len(should_be_higher),
                "less_important": len(less_important),
            },
        }

    except Exception as e:
        return {"error": f"LLM call failed: {e!s}"}


@router.post("/prompts/{name}/apply-suggestion")
async def apply_suggestion(
    request: Request,
    name: str,
    suggestion: PromptUpdate,
) -> dict[str, Any]:
    """Apply an LLM-suggested prompt update."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        new_version = upsert_prompt(conn, name, suggestion.template, "llm")
        conn.commit()

    return {
        "name": name,
        "version": new_version,
        "message": "LLM suggestion applied",
    }
