"""Canonical enums for signal tiers, pipeline stages, and tweet categories."""

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """Backport of StrEnum for Python <3.11."""


class SignalTier(StrEnum):
    """Signal tier classification for processed tweets.

    StrEnum ensures backward compatibility with SQLite TEXT columns,
    JSON serialization, and LLM prompt templates.
    """

    NOISE = "noise"
    NEWS = "news"
    MARKET_RELEVANT = "market_relevant"
    HIGH_SIGNAL = "high_signal"


class PipelineStage(StrEnum):
    """Processing pipeline stages used as future tags in triage."""

    SUMMARY = "summary"
    MEDIA = "media"
    ARTICLE = "article"
    ENRICH = "enrich"


class Category(StrEnum):
    """Tweet content categories assigned during triage scoring."""

    FED_POLICY = "fed_policy"
    INFLATION = "inflation"
    JOB_MARKET = "job_market"
    MACRO_DATA = "macro_data"
    EARNINGS = "earnings"
    EQUITIES = "equities"
    RATES_FX = "rates_fx"
    CREDIT = "credit"
    BANKS = "banks"
    CONSUMER_SPENDING = "consumer_spending"
    CAPEX = "capex"
    COMMODITIES = "commodities"
    ENERGY = "energy"
    METALS_MINING = "metals_mining"
    GEOPOLITICAL = "geopolitical"
    SANCTIONS = "sanctions"
    TECH_BUSINESS = "tech_business"
    AI_ADVANCEMENT = "ai_advancement"
    CRYPTO = "crypto"
    NOISE = "noise"


# Canonical ranking for signal tier comparison.
SIGNAL_TIER_RANK: dict[str, int] = {
    SignalTier.NOISE: 0,
    SignalTier.NEWS: 1,
    SignalTier.MARKET_RELEVANT: 2,
    SignalTier.HIGH_SIGNAL: 3,
}
