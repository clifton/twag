"""Scoring, triage, enrichment, and analysis functions."""

from dataclasses import dataclass, field
from typing import Any

from twag.config import load_config

from .llm_client import _call_llm, _call_llm_vision, _parse_json_response
from .prompts import (
    ARTICLE_SUMMARY_PROMPT,
    BATCH_TRIAGE_PROMPT,
    DOCUMENT_SUMMARY_PROMPT,
    ENRICHMENT_PROMPT,
    MEDIA_PROMPT,
    SUMMARIZE_PROMPT,
    TRIAGE_PROMPT,
)


@dataclass
class TriageResult:
    """Result of tweet triage scoring."""

    tweet_id: str
    score: float
    categories: list[str]
    summary: str
    tickers: list[str] = field(default_factory=list)


@dataclass
class EnrichmentResult:
    """Result of tweet enrichment analysis."""

    signal_tier: str
    insight: str
    implications: str
    narratives: list[str] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)


@dataclass
class VisionResult:
    """Result of chart/image analysis."""

    chart_type: str
    description: str
    insight: str
    implication: str
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


def triage_tweet(
    tweet_id: str,
    tweet_text: str,
    handle: str,
    model: str | None = None,
    provider: str | None = None,
) -> TriageResult:
    """Score a single tweet for relevance."""
    config = load_config()
    model = model or config["llm"]["triage_model"]
    provider = provider or config["llm"].get("triage_provider", "anthropic")

    prompt = TRIAGE_PROMPT.format(tweet_text=tweet_text, handle=handle)
    text = _call_llm(provider, model, prompt, max_tokens=512)
    data = _parse_json_response(text)

    if isinstance(data, list):
        data = data[0]

    # Handle both old "category" (string) and new "categories" (array) format
    categories = data.get("categories") or [data.get("category", "noise")]
    if isinstance(categories, str):
        categories = [categories]

    return TriageResult(
        tweet_id=tweet_id,
        score=float(data.get("score", 0)),
        categories=categories,
        summary=data.get("summary", ""),
        tickers=data.get("tickers", []),
    )


def triage_tweets_batch(
    tweets: list[dict[str, str]],
    model: str | None = None,
    provider: str | None = None,
) -> list[TriageResult]:
    """Score multiple tweets in a single API call.

    Args:
        tweets: List of dicts with 'id', 'text', 'handle' keys
        model: Model to use (defaults to config triage_model)
        provider: Provider to use (defaults to config triage_provider)
    """
    if not tweets:
        return []

    config = load_config()
    model = model or config["llm"]["triage_model"]
    provider = provider or config["llm"].get("triage_provider", "anthropic")

    # Format tweets for prompt
    tweets_text = "\n\n".join(f"[{t['id']}] @{t['handle']}: {t['text']}" for t in tweets)

    prompt = BATCH_TRIAGE_PROMPT.format(tweets=tweets_text)
    text = _call_llm(provider, model, prompt, max_tokens=16384)
    data = _parse_json_response(text)

    if not isinstance(data, list):
        data = [data]

    results = []
    for item in data:
        # Handle both old "category" (string) and new "categories" (array) format
        categories = item.get("categories") or [item.get("category", "noise")]
        if isinstance(categories, str):
            categories = [categories]

        results.append(
            TriageResult(
                tweet_id=str(item.get("id", "")),
                score=float(item.get("score", 0)),
                categories=categories,
                summary=item.get("summary", ""),
                tickers=item.get("tickers", []),
            )
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

    text = _call_llm(provider, model, prompt, max_tokens=2048, reasoning=reasoning)
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
    text = _call_llm(provider, model, prompt, max_tokens=1024, reasoning=reasoning)

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
    text = _call_llm(provider, model, prompt, max_tokens=256, reasoning=reasoning)
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

    prompt = ARTICLE_SUMMARY_PROMPT.format(
        article_title=(article_title or "").strip() or "[untitled]",
        article_preview=(article_preview or "").strip() or "[none]",
        article_text=clean_text,
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
            text = _call_llm(cand_provider, cand_model, prompt, max_tokens=4096, reasoning=reasoning)
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
                }
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
                }
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

    text = _call_llm_vision(provider, model, image_url, MEDIA_PROMPT, max_tokens=4096)
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
