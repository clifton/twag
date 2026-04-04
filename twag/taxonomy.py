"""Canonical constants for tweet classification axes.

Every scoring, routing, and display decision that references a signal tier,
category, media kind, or reaction type should import from here instead of
using inline string literals.  Prompt text in scorer/prompts.py and
db/prompts.py is intentionally left as-is (LLM instruction strings).
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """Minimal StrEnum backport for Python 3.10."""

# ── Signal tier ──────────────────────────────────────────────────────────


class SignalTier(StrEnum):
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


def score_to_signal_tier(score: float) -> str:
    """Map a numeric relevance score to its signal tier string."""
    if score >= 8:
        return SignalTier.HIGH_SIGNAL
    if score >= 6:
        return SignalTier.MARKET_RELEVANT
    if score >= 4:
        return SignalTier.NEWS
    return SignalTier.NOISE


# ── Category ─────────────────────────────────────────────────────────────


class Category(StrEnum):
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


# ── Media kind ───────────────────────────────────────────────────────────


class MediaKind(StrEnum):
    CHART = "chart"
    TABLE = "table"
    DOCUMENT = "document"
    SCREENSHOT = "screenshot"
    MEME = "meme"
    PHOTO = "photo"
    OTHER = "other"


# ── Reaction type ────────────────────────────────────────────────────────


class ReactionType(StrEnum):
    BOOST = ">>"
    UP = ">"
    DOWN = "<"
    MUTE_AUTHOR = "x_author"
    MUTE_TOPIC = "x_topic"
