"""LLM-powered tweet scoring and analysis."""

from .llm_client import (
    _call_llm,
    _call_llm_vision,
    _parse_json_response,
    get_anthropic_client,
    get_gemini_client,
)
from .scoring import (
    EnrichmentResult,
    MediaAnalysisResult,
    TriageResult,
    XArticleSummaryResult,
    analyze_image,
    analyze_media,
    enrich_tweet,
    summarize_document_text,
    summarize_tweet,
    summarize_x_article,
    triage_tweets_batch,
)

__all__ = [
    "EnrichmentResult",
    "MediaAnalysisResult",
    "TriageResult",
    "VisionResult",
    "XArticleSummaryResult",
    "_call_llm",
    "_call_llm_vision",
    "_parse_json_response",
    "analyze_image",
    "analyze_media",
    "enrich_tweet",
    "get_anthropic_client",
    "get_gemini_client",
    "summarize_document_text",
    "summarize_tweet",
    "summarize_x_article",
    "triage_tweet",
    "triage_tweets_batch",
]


def __getattr__(name: str):
    if name == "VisionResult":
        from twag._compat import _deprecated

        _deprecated("twag.scorer.VisionResult", "twag.scorer.MediaAnalysisResult")
        return MediaAnalysisResult

    if name == "triage_tweet":
        from twag._compat import _deprecated

        _deprecated("twag.scorer.triage_tweet", "twag.scorer.triage_tweets_batch")

        def triage_tweet(
            tweet_id: str,
            tweet_text: str,
            handle: str,
            model: str | None = None,
            provider: str | None = None,
        ) -> TriageResult:
            """Deprecated single-tweet triage — wraps triage_tweets_batch."""
            results = triage_tweets_batch(
                [{"id": tweet_id, "text": tweet_text, "handle": handle}],
                model=model,
                provider=provider,
            )
            return (
                results[0]
                if results
                else TriageResult(
                    tweet_id=tweet_id,
                    score=0.0,
                    categories=[],
                    summary="",
                    tickers=[],
                )
            )

        return triage_tweet

    raise AttributeError(f"module 'twag.scorer' has no attribute {name!r}")
