"""Centralized event taxonomy: signal tiers, categories, reaction types, task tags."""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """Backport of StrEnum for Python <3.11."""


class SignalTier(StrEnum):
    """Tweet signal classification tiers, ordered from lowest to highest."""

    NOISE = "noise"
    NEWS = "news"
    MARKET_RELEVANT = "market_relevant"
    HIGH_SIGNAL = "high_signal"


SIGNAL_TIER_RANK: dict[str, int] = {
    SignalTier.NOISE: 0,
    SignalTier.NEWS: 1,
    SignalTier.MARKET_RELEVANT: 2,
    SignalTier.HIGH_SIGNAL: 3,
}


class Category(StrEnum):
    """Tweet categorization labels used in triage and enrichment prompts."""

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


CATEGORIES_CSV = ", ".join(member.value for member in Category)


class ReactionType(StrEnum):
    """User reaction types stored in the reactions table."""

    BOOST = ">>"
    UPVOTE = ">"
    DOWNVOTE = "<"
    MUTE_AUTHOR = "x_author"
    MUTE_TOPIC = "x_topic"


class TaskTag(StrEnum):
    """Internal task tags for parallel pipeline work units."""

    SUMMARY = "summary"
    MEDIA = "media"
    ARTICLE = "article"
    ENRICH = "enrich"
