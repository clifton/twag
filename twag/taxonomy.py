"""Central taxonomy for signal tiers, content categories, and metric names.

StrEnum values compare equal to plain strings, so existing DB data, test
assertions, and serialized payloads continue to work without migration.
"""

from enum import StrEnum  # ty: ignore[unresolved-import]


class SignalTier(StrEnum):
    NOISE = "noise"
    NEWS = "news"
    MARKET_RELEVANT = "market_relevant"
    HIGH_SIGNAL = "high_signal"

    def rank(self) -> int:
        return _TIER_RANK[self]


_TIER_RANK: dict[SignalTier, int] = {  # ty: ignore[invalid-assignment]
    SignalTier.NOISE: 0,
    SignalTier.NEWS: 1,
    SignalTier.MARKET_RELEVANT: 2,
    SignalTier.HIGH_SIGNAL: 3,
}


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


DRY_RUN_CATEGORY = "dry_run"

CATEGORY_LIST_CSV = ", ".join(c.value for c in Category)  # ty: ignore[not-iterable]


class Metric:
    """Metric name constants organized by subsystem."""

    # -- fetcher --
    FETCHER_CALLS = "fetcher.calls"
    FETCHER_ERRORS = "fetcher.errors"
    FETCHER_RETRIES = "fetcher.retries"
    FETCHER_LATENCY = "fetcher.latency_seconds"

    # -- scorer --
    SCORER_ANTHROPIC_CALLS = "scorer.anthropic.calls"
    SCORER_ANTHROPIC_ERRORS = "scorer.anthropic.errors"
    SCORER_ANTHROPIC_LATENCY = "scorer.anthropic.latency_seconds"
    SCORER_ANTHROPIC_INPUT_TOKENS = "scorer.anthropic.input_tokens"
    SCORER_ANTHROPIC_OUTPUT_TOKENS = "scorer.anthropic.output_tokens"
    SCORER_GEMINI_CALLS = "scorer.gemini.calls"
    SCORER_GEMINI_ERRORS = "scorer.gemini.errors"
    SCORER_GEMINI_LATENCY = "scorer.gemini.latency_seconds"
    SCORER_RETRIES = "scorer.retries"

    # -- pipeline --
    PIPELINE_TRIAGE_PROCESSED = "pipeline.triage.processed"
    PIPELINE_TRIAGE_BATCH_ERRORS = "pipeline.triage.batch_errors"
    PIPELINE_PROCESS_LATENCY = "pipeline.process_unprocessed.latency_seconds"
    PIPELINE_PROCESS_TWEETS = "pipeline.process_unprocessed.tweets"

    # -- web --
    WEB_HTTP_REQUESTS = "web.http.requests"
    WEB_HTTP_LATENCY = "web.http.latency_seconds"
