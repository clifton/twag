"""Scoring, triage, enrichment, and analysis functions."""

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from twag.config import load_config
from twag.taxonomy import categories_line

from .llm_client import _call_llm, _call_llm_vision, _parse_json_response
from .prompts import (
    ARTICLE_SUMMARY_PROMPT,
    BATCH_TRIAGE_PROMPT,
    DOCUMENT_SUMMARY_PROMPT,
    ENRICHMENT_PROMPT,
    MEDIA_PROMPT,
    SUMMARIZE_PROMPT,
)

log = logging.getLogger(__name__)

FUND_CONTEXT_PATH = Path.home() / "clawd" / "state" / "registry" / "twag-context.md"
GENERATED_FUND_CONTEXT_PATH = Path.home() / "clawd" / "state" / "registry" / "CONTEXT.md"
TRIAGE_PROMPT_PLACEHOLDERS = ("{tweets}", "{fund_context}", "{categories}")
PLAYBOOK_TRIGGERS = [
    "supply_shock",
    "supercycle",
    "vol_substitution",
    "ai_victim",
    "event_reset",
    "dat_mnav",
    "defensive_break",
]

TRIAGE_BATCH_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "score": {"type": "number"},
            "surprise": {"type": "integer"},
            "is_stale_repeat": {"type": "boolean"},
            "categories": {"type": "array", "items": {"type": "string"}},
            "themes": {"type": "array", "items": {"type": "string"}},
            "playbook_trigger": {"type": "string", "enum": [*PLAYBOOK_TRIGGERS, "none"]},
            "catalyst": {"type": "string", "enum": ["scheduled", "resolved", "none"]},
            "direction": {"type": "string", "enum": ["long", "short", "na"]},
            "tickers": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
        "required": [
            "id",
            "score",
            "surprise",
            "is_stale_repeat",
            "categories",
            "themes",
            "playbook_trigger",
            "catalyst",
            "direction",
            "tickers",
            "summary",
        ],
        "additionalProperties": False,
    },
}


@dataclass
class TriageResult:
    """Result of tweet triage scoring."""

    tweet_id: str
    score: float
    categories: list[str]
    summary: str
    tickers: list[str] = field(default_factory=list)
    surprise: int = 0
    is_stale_repeat: bool = False
    themes: list[str] = field(default_factory=list)
    playbook_trigger: str | None = None
    catalyst_status: str | None = None
    direction: str = "na"


@dataclass
class EnrichmentResult:
    """Result of tweet enrichment analysis."""

    signal_tier: str
    insight: str
    implications: str
    narratives: list[str] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)


@dataclass
class MediaAnalysisResult:
    """Result of image/media analysis."""

    kind: str
    short_description: str
    prose_text: str
    prose_summary: str
    chart: dict[str, Any] = field(default_factory=dict)
    table: dict[str, Any] = field(default_factory=dict)


@dataclass
class XArticleSummaryResult:
    """Structured summary for X native article payloads."""

    short_summary: str
    primary_points: list[dict[str, Any]] = field(default_factory=list)
    actionable_items: list[dict[str, Any]] = field(default_factory=list)


def _bounded_article_text(article_text: str, max_chars: int) -> str:
    """Bound long article bodies while preserving the opening and closing context."""
    clean_text = (article_text or "").strip()
    if len(clean_text) <= max_chars:
        return clean_text
    if max_chars <= 1000:
        return clean_text[:max_chars].strip()

    head_chars = int(max_chars * 0.75)
    tail_chars = max_chars - head_chars
    return (
        clean_text[:head_chars].rstrip()
        + "\n\n[...middle truncated to reduce analysis cost...]\n\n"
        + clean_text[-tail_chars:].lstrip()
    )


def render_triage_prompt(
    template: str,
    *,
    tweets: str,
    fund_context: str,
    categories: str,
) -> str:
    """Render only the three supported placeholders without interpreting braces."""
    rendered = template
    rendered = rendered.replace("{tweets}", tweets)
    rendered = rendered.replace("{fund_context}", fund_context)
    return rendered.replace("{categories}", categories)


def resolve_triage_template(conn: sqlite3.Connection) -> str:
    """Return the editable batch prompt or a safe built-in fallback."""
    from twag.db.prompts import get_prompt
    from twag.metrics import get_collector

    prompt = get_prompt(conn, "batch_triage")
    if prompt and all(placeholder in prompt.template for placeholder in TRIAGE_PROMPT_PLACEHOLDERS):
        return prompt.template

    reason = "missing" if prompt is None else "missing required placeholders"
    log.error("batch_triage prompt %s; using built-in prompt", reason)
    get_collector().inc("pipeline.triage.prompt_fallback")
    return BATCH_TRIAGE_PROMPT


def resolve_fund_context_path() -> Path:
    """Pick the context file scoring will read: the freshest existing candidate.

    The spine repo only regenerates GENERATED_FUND_CONTEXT_PATH (CONTEXT.md);
    FUND_CONTEXT_PATH (twag-context.md) is a hand-seeded stopgap. Any freshness
    monitoring must evaluate this same candidate set.
    """
    candidates = [candidate for candidate in (GENERATED_FUND_CONTEXT_PATH, FUND_CONTEXT_PATH) if candidate.exists()]
    return max(candidates, key=lambda candidate: candidate.stat().st_mtime) if candidates else FUND_CONTEXT_PATH


def load_fund_context(
    path: Path | None = None,
    *,
    max_age_seconds: float = 48 * 60 * 60,
) -> tuple[str, bool]:
    """Load fresh fund context; stale or unreadable context degrades to empty."""
    import time

    context_path = path if path is not None else resolve_fund_context_path()
    try:
        stat = context_path.stat()
        if time.time() - stat.st_mtime > max_age_seconds:
            return "", True
        return context_path.read_text().strip(), False
    except OSError:
        return "", True


def triage_tweets_batch(
    tweets: list[dict[str, str]],
    model: str | None = None,
    provider: str | None = None,
    *,
    prompt_template: str | None = None,
    fund_context: str = "",
) -> list[TriageResult]:
    """Score multiple tweets in a single API call.

    Args:
        tweets: List of dicts with id, text, handle, and optional author_context keys
        model: Model to use (defaults to config triage_model)
        provider: Provider to use (defaults to config triage_provider)
    """
    if not tweets:
        return []

    config = load_config()
    model = model or config["llm"]["triage_model"]
    provider = provider or config["llm"].get("triage_provider", "anthropic")

    # Format tweets for prompt
    tweets_text = "\n\n".join(
        f"[{t['id']}] @{t['handle']} ({t.get('author_context') or 'unranked'}): {t['text']}" for t in tweets
    )

    prompt = render_triage_prompt(
        prompt_template or BATCH_TRIAGE_PROMPT,
        tweets=tweets_text,
        fund_context=fund_context or "[unavailable]",
        categories=categories_line(),
    )
    text = _call_llm(
        provider,
        model,
        prompt,
        max_tokens=16384,
        component="triage",
        json_schema=TRIAGE_BATCH_SCHEMA,
    )
    data = _parse_json_response(text)

    if not isinstance(data, list):
        data = [data]

    results = []
    for item in data:
        # Handle both old "category" (string) and new "categories" (array) format
        categories = item.get("categories") or [item.get("category", "noise")]
        if isinstance(categories, str):
            categories = [categories]

        surprise = item.get("surprise", 0)
        try:
            surprise = max(0, min(2, int(surprise)))
        except (TypeError, ValueError):
            surprise = 0
        playbook_trigger = item.get("playbook_trigger")
        if playbook_trigger not in PLAYBOOK_TRIGGERS:
            playbook_trigger = None
        catalyst_status = item.get("catalyst")
        if catalyst_status not in {"scheduled", "resolved"}:
            catalyst_status = None
        direction = item.get("direction", "na")
        if direction not in {"long", "short", "na"}:
            direction = "na"

        results.append(
            TriageResult(
                tweet_id=str(item.get("id", "")),
                score=float(item.get("score", 0)),
                categories=categories,
                summary=item.get("summary", ""),
                tickers=item.get("tickers", []),
                surprise=surprise,
                is_stale_repeat=bool(item.get("is_stale_repeat", False)),
                themes=item.get("themes", []) if isinstance(item.get("themes", []), list) else [],
                playbook_trigger=playbook_trigger,
                catalyst_status=catalyst_status,
                direction=direction,
            ),
        )

    return results


def enrich_tweet(
    tweet_text: str,
    handle: str,
    author_category: str = "unknown",
    quoted_tweet: str = "",
    article_summary: str = "",
    image_description: str = "",
    model: str | None = None,
    provider: str | None = None,
) -> EnrichmentResult:
    """Deep analysis of a high-signal tweet."""
    config = load_config()
    model = model or config["llm"]["enrichment_model"]
    provider = provider or config["llm"].get("enrichment_provider", "anthropic")
    reasoning = config["llm"].get("enrichment_reasoning")

    prompt = ENRICHMENT_PROMPT.format(
        tweet_text=tweet_text,
        handle=handle,
        author_category=author_category,
        quoted_tweet=quoted_tweet or "[none]",
        article_summary=article_summary or "[none]",
        image_description=image_description or "[none]",
    )

    text = _call_llm(provider, model, prompt, max_tokens=2048, reasoning=reasoning, component="enrichment")
    data = _parse_json_response(text)

    if isinstance(data, list):
        data = data[0]

    return EnrichmentResult(
        signal_tier=data.get("signal_tier", "noise"),
        insight=data.get("insight", ""),
        implications=data.get("implications", ""),
        narratives=data.get("narratives", []),
        tickers=data.get("tickers", []),
    )


def summarize_tweet(
    tweet_text: str,
    handle: str,
    model: str | None = None,
    provider: str | None = None,
) -> str:
    """Summarize a long tweet. Uses enrichment model by default."""
    config = load_config()
    model = model or config["llm"]["enrichment_model"]
    provider = provider or config["llm"].get("enrichment_provider", "anthropic")
    reasoning = config["llm"].get("enrichment_reasoning")

    prompt = SUMMARIZE_PROMPT.format(tweet_text=tweet_text, handle=handle)
    text = _call_llm(provider, model, prompt, max_tokens=1024, reasoning=reasoning, component="summarization")

    # Return raw text (not JSON)
    return text.strip()


def summarize_document_text(
    document_text: str,
    model: str | None = None,
    provider: str | None = None,
) -> str:
    """Summarize OCR document text into two concise lines."""
    config = load_config()
    model = model or config["llm"]["enrichment_model"]
    provider = provider or config["llm"].get("enrichment_provider", "anthropic")
    reasoning = config["llm"].get("enrichment_reasoning")

    prompt = DOCUMENT_SUMMARY_PROMPT.format(document_text=document_text)
    text = _call_llm(provider, model, prompt, max_tokens=256, reasoning=reasoning, component="document_summary")
    return text.strip()


def summarize_x_article(
    article_text: str,
    *,
    article_title: str = "",
    article_preview: str = "",
    model: str | None = None,
    provider: str | None = None,
) -> XArticleSummaryResult:
    """Summarize and structure an X-native article body."""
    config = load_config()
    model = model or config["llm"]["enrichment_model"]
    provider = provider or config["llm"].get("enrichment_provider", "anthropic")
    reasoning = config["llm"].get("enrichment_reasoning")

    clean_text = (article_text or "").strip()
    if not clean_text:
        return XArticleSummaryResult(short_summary=(article_preview or article_title or "").strip())

    fallback_summary = (article_preview or article_title or clean_text[:400]).strip()
    try:
        max_article_chars = int(config.get("scoring", {}).get("max_article_summary_chars", 20_000))
    except (TypeError, ValueError):
        max_article_chars = 20_000
    bounded_text = _bounded_article_text(clean_text, max_article_chars)

    prompt = ARTICLE_SUMMARY_PROMPT.format(
        article_title=(article_title or "").strip() or "[untitled]",
        article_preview=(article_preview or "").strip() or "[none]",
        article_text=bounded_text,
    )

    fallback_provider = config["llm"].get("triage_provider", "gemini")
    fallback_model = config["llm"].get("triage_model", model)
    candidates: list[tuple[str, str]] = []
    for cand_provider, cand_model in [
        (provider, model),
        (fallback_provider, fallback_model),
    ]:
        pair = (cand_provider, cand_model)
        if pair not in candidates:
            candidates.append(pair)

    data: dict[str, Any] | list[dict[str, Any]] | None = None
    for cand_provider, cand_model in candidates:
        try:
            text = _call_llm(
                cand_provider,
                cand_model,
                prompt,
                max_tokens=4096,
                reasoning=reasoning,
                component="article",
            )
            data = _parse_json_response(text)
            break
        except Exception:
            continue

    if data is None:
        return XArticleSummaryResult(short_summary=fallback_summary)

    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return XArticleSummaryResult(short_summary=fallback_summary)

    short_summary = (data.get("short_summary") or "").strip()
    if not short_summary:
        short_summary = fallback_summary

    primary_points_raw = data.get("primary_points")
    primary_points: list[dict[str, Any]] = []
    if isinstance(primary_points_raw, list):
        for item in primary_points_raw:
            if not isinstance(item, dict):
                continue
            point = (item.get("point") or "").strip()
            reasoning_text = (item.get("reasoning") or "").strip()
            evidence = (item.get("evidence") or "").strip()
            if not point:
                continue
            primary_points.append(
                {
                    "point": point,
                    "reasoning": reasoning_text,
                    "evidence": evidence,
                },
            )

    action_raw = data.get("actionable_items")
    actionable_items: list[dict[str, Any]] = []
    if isinstance(action_raw, list):
        for item in action_raw:
            if not isinstance(item, dict):
                continue
            action = (item.get("action") or "").strip()
            if not action:
                continue
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))
            tickers = item.get("tickers") if isinstance(item.get("tickers"), list) else []
            actionable_items.append(
                {
                    "action": action,
                    "trigger": (item.get("trigger") or "").strip(),
                    "horizon": (item.get("horizon") or "").strip(),
                    "confidence": confidence,
                    "tickers": [str(t).upper() for t in tickers if isinstance(t, str) and t.strip()],
                },
            )

    return XArticleSummaryResult(
        short_summary=short_summary,
        primary_points=primary_points[:6],
        actionable_items=actionable_items,
    )


def analyze_image(
    image_url: str,
    model: str | None = None,
    provider: str | None = None,
) -> MediaAnalysisResult:
    """Analyze a chart or image from a tweet."""
    config = load_config()
    model = model or config["llm"]["vision_model"]
    provider = provider or config["llm"].get("vision_provider", "anthropic")

    text = _call_llm_vision(provider, model, image_url, MEDIA_PROMPT, max_tokens=4096, component="vision")
    data = _parse_json_response(text)

    if isinstance(data, list):
        data = data[0]

    chart = data.get("chart") or {}
    if not isinstance(chart, dict):
        chart = {}

    table = data.get("table") or {}
    if not isinstance(table, dict):
        table = {}

    return MediaAnalysisResult(
        kind=(data.get("kind", "other") or "other").lower(),
        short_description=(data.get("short_description") or "").strip(),
        prose_text=(data.get("prose_text") or "").strip(),
        prose_summary=(data.get("prose_summary") or "").strip(),
        chart={
            "type": chart.get("type", ""),
            "description": chart.get("description", ""),
            "insight": chart.get("insight", ""),
            "implication": chart.get("implication", ""),
            "tickers": chart.get("tickers", []),
        },
        table={
            "title": table.get("title", ""),
            "description": table.get("description", ""),
            "columns": table.get("columns", []),
            "rows": table.get("rows", []),
            "summary": table.get("summary", ""),
            "tickers": table.get("tickers", []),
        },
    )


def analyze_media(
    image_url: str,
    model: str | None = None,
    provider: str | None = None,
) -> MediaAnalysisResult:
    """Analyze any tweet media image with OCR and classification."""
    return analyze_image(image_url=image_url, model=model, provider=provider)
