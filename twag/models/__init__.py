"""Backward-compatibility shim for twag.models (removed in v0.2).

The twag.models package was removed because its Pydantic mirrors of internal
dataclasses were unused. This shim re-exports the canonical types so that
existing ``from twag.models import ...`` statements keep working temporarily.
"""

from __future__ import annotations

import warnings

# Link normalization — canonical home is twag.link_utils
from twag.link_utils import LinkNormalizationResult

# Scoring result types — canonical home is twag.scorer.scoring
from twag.scorer.scoring import (
    EnrichmentResult,
    MediaAnalysisResult,
    TriageResult,
    XArticleSummaryResult,
)


def __getattr__(name: str):
    _REMOVED = {
        # Former twag.models.scoring
        "VisionResult": ("twag.scorer.MediaAnalysisResult", MediaAnalysisResult),
        "PrimaryPoint": None,
        "ActionableItem": None,
        # Former twag.models.api
        "QuoteEmbed": None,
        "CategoryCount": None,
        "TickerCount": None,
        "TweetResponse": None,
        "TweetListResponse": None,
        # Former twag.models.config
        "LLMConfig": None,
        "ScoringConfig": None,
        "NotificationConfig": None,
        "AccountsConfig": None,
        "FetchConfig": None,
        "ProcessingConfig": None,
        "PathsConfig": None,
        "BirdConfig": None,
        "TwagConfig": None,
        # Former twag.models.db_models
        "SearchResult": None,
        "Reaction": None,
        "Prompt": None,
        "ContextCommand": None,
        "FeedTweet": None,
        # Former twag.models.links
        "TweetLink": None,
        "InlineTweetLink": None,
        "ExternalLink": None,
        # Former twag.models.media
        "ChartAnalysis": None,
        "TableAnalysis": None,
        "MediaItem": None,
        # Former twag.models.tweet
        "TweetData": None,
    }

    if name in _REMOVED:
        entry = _REMOVED[name]
        if entry is not None:
            new_name, obj = entry
            warnings.warn(
                f"twag.models.{name} is deprecated and will be removed in v0.3. Use {new_name} instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            return obj
        warnings.warn(
            f"twag.models.{name} was removed in v0.2 and has no replacement.",
            DeprecationWarning,
            stacklevel=2,
        )
        raise AttributeError(f"twag.models.{name} was removed in v0.2 with no replacement")

    raise AttributeError(f"module 'twag.models' has no attribute {name!r}")


__all__ = [
    "EnrichmentResult",
    "LinkNormalizationResult",
    "MediaAnalysisResult",
    "TriageResult",
    "XArticleSummaryResult",
]
