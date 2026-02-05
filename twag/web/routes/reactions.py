"""Reaction API routes."""

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ...db import (
    delete_reaction,
    get_connection,
    get_reactions_for_tweet,
    get_reactions_summary,
    get_reactions_with_tweets,
    insert_reaction,
    mute_account,
)

router = APIRouter(tags=["reactions"])


class ReactionCreate(BaseModel):
    """Request body for creating a reaction."""

    tweet_id: str
    reaction_type: str  # '>>', '>', '<', 'x_author', 'x_topic'
    reason: str | None = None
    target: str | None = None  # author handle or category for X reactions


@router.post("/react")
async def create_reaction(request: Request, reaction: ReactionCreate) -> dict[str, Any]:
    """
    Create a reaction to a tweet.

    Reaction types:
    - '>>' : High importance - "This should be top-tier"
    - '>'  : Should be higher - "This was underrated"
    - '<'  : Less important - "This was overrated"
    - 'x_author' : Mute author (requires target=author_handle)
    - 'x_topic'  : Mute topic (requires target=category)
    """
    db_path = request.app.state.db_path

    # Validate reaction type
    valid_types = {">>", ">", "<", "x_author", "x_topic"}
    if reaction.reaction_type not in valid_types:
        return {"error": f"Invalid reaction type. Must be one of: {valid_types}"}

    # Handle mute actions
    if reaction.reaction_type == "x_author":
        if not reaction.target:
            return {"error": "target (author handle) required for x_author reaction"}

        with get_connection(db_path) as conn:
            mute_account(conn, reaction.target)
            reaction_id = insert_reaction(
                conn,
                reaction.tweet_id,
                reaction.reaction_type,
                reaction.reason,
                reaction.target,
            )
            conn.commit()

        return {
            "id": reaction_id,
            "message": f"Author @{reaction.target} muted",
        }

    # For x_topic, just record the reaction (could extend to ignore list later)
    with get_connection(db_path) as conn:
        reaction_id = insert_reaction(
            conn,
            reaction.tweet_id,
            reaction.reaction_type,
            reaction.reason,
            reaction.target,
        )
        conn.commit()

    return {
        "id": reaction_id,
        "tweet_id": reaction.tweet_id,
        "reaction_type": reaction.reaction_type,
    }


@router.get("/reactions/{tweet_id}")
async def get_tweet_reactions(request: Request, tweet_id: str) -> dict[str, Any]:
    """Get all reactions for a specific tweet."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        reactions = get_reactions_for_tweet(conn, tweet_id)

    return {
        "tweet_id": tweet_id,
        "reactions": [
            {
                "id": r.id,
                "reaction_type": r.reaction_type,
                "reason": r.reason,
                "target": r.target,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reactions
        ],
    }


@router.delete("/reactions/{reaction_id}")
async def remove_reaction(request: Request, reaction_id: int) -> dict[str, Any]:
    """Delete a reaction."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        deleted = delete_reaction(conn, reaction_id)
        conn.commit()

    if deleted:
        return {"message": "Reaction deleted"}
    return {"error": "Reaction not found"}


@router.get("/reactions/summary")
async def reactions_summary(request: Request) -> dict[str, Any]:
    """Get summary of reaction counts by type."""
    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        summary = get_reactions_summary(conn)

    return {"summary": summary}


@router.get("/reactions/export")
async def export_reactions(
    request: Request,
    reaction_type: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Export reactions with associated tweet data.
    Useful for prompt tuning analysis.
    """
    import json

    db_path = request.app.state.db_path

    with get_connection(db_path) as conn:
        results = get_reactions_with_tweets(conn, reaction_type, limit)

    export_data = []
    for reaction, tweet in results:
        # Parse categories
        categories = []
        if tweet["category"]:
            try:
                categories = json.loads(tweet["category"])
            except json.JSONDecodeError:
                categories = [tweet["category"]]

        export_data.append(
            {
                "reaction": {
                    "id": reaction.id,
                    "type": reaction.reaction_type,
                    "reason": reaction.reason,
                    "created_at": reaction.created_at.isoformat() if reaction.created_at else None,
                },
                "tweet": {
                    "id": tweet["id"],
                    "author": tweet["author_handle"],
                    "content": tweet["content"][:500],  # Truncate for export
                    "summary": tweet["summary"],
                    "score": tweet["relevance_score"],
                    "categories": categories,
                    "signal_tier": tweet["signal_tier"],
                },
            }
        )

    return {
        "count": len(export_data),
        "reactions": export_data,
    }
