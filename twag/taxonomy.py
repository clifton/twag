"""Single source of truth for coarse tweet categories."""

CATEGORIES: list[str] = [
    "fed_policy",
    "inflation",
    "job_market",
    "macro_data",
    "earnings",
    "equities",
    "rates_fx",
    "credit",
    "banks",
    "consumer_spending",
    "capex",
    "commodities",
    "energy",
    "metals_mining",
    "geopolitical",
    "sanctions",
    "tech_business",
    "ai_advancement",
    "crypto",
    "noise",
]


def categories_line() -> str:
    """Return categories in the compact form used by scorer prompts."""
    return ", ".join(CATEGORIES)
