"""Retroactive LLM cost estimation from DB state."""

from __future__ import annotations

from dataclasses import dataclass

# Default per-call token budgets (input_tokens, output_tokens)
DEFAULT_TOKEN_BUDGETS: dict[str, tuple[int, int]] = {
    "triage": (2000, 1000),
    "enrichment": (1500, 1000),
    "vision": (1000, 1000),
    "summarize": (1000, 500),
    "article": (3000, 2000),
}

# Pricing: $/1K tokens (input, output) per model
DEFAULT_MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash-preview": (0.00015, 0.0006),
    "gemini-2.5-pro-preview": (0.00125, 0.01),
    "claude-sonnet-4-20250514": (0.003, 0.015),
    "claude-haiku-4-5-20251001": (0.0008, 0.004),
}

# Default model used for each component
DEFAULT_COMPONENT_MODELS: dict[str, str] = {
    "triage": "gemini-2.5-flash-preview",
    "enrichment": "gemini-2.5-flash-preview",
    "vision": "gemini-2.5-flash-preview",
    "summarize": "gemini-2.5-flash-preview",
    "article": "gemini-2.5-flash-preview",
}


@dataclass
class ComponentCost:
    """Cost estimate for a single pipeline component."""

    component: str
    call_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


def estimate_costs(
    counts: dict[str, int],
    token_budgets: dict[str, tuple[int, int]] | None = None,
    model_prices: dict[str, tuple[float, float]] | None = None,
    component_models: dict[str, str] | None = None,
) -> list[ComponentCost]:
    """Estimate LLM costs from DB call counts.

    Args:
        counts: Dict mapping component names to call counts
            (tweets_triaged, tweets_enriched, tweets_with_media_analysis,
             tweets_summarized, articles_processed).
        token_budgets: Override per-call token budgets.
        model_prices: Override model pricing ($/1K tokens).
        component_models: Override which model each component uses.

    Returns:
        List of ComponentCost entries.
    """
    budgets = {**DEFAULT_TOKEN_BUDGETS, **(token_budgets or {})}
    prices = {**DEFAULT_MODEL_PRICES, **(model_prices or {})}
    models = {**DEFAULT_COMPONENT_MODELS, **(component_models or {})}

    # Map DB count keys to component names
    count_map: dict[str, str] = {
        "triage": "tweets_triaged",
        "enrichment": "tweets_enriched",
        "vision": "tweets_with_media_analysis",
        "summarize": "tweets_summarized",
        "article": "articles_processed",
    }

    results: list[ComponentCost] = []
    for component, count_key in count_map.items():
        call_count = counts.get(count_key, 0)
        in_tok, out_tok = budgets.get(component, (0, 0))
        total_in = call_count * in_tok
        total_out = call_count * out_tok

        model = models.get(component, "gemini-2.5-flash-preview")
        price_in, price_out = prices.get(model, (0.0, 0.0))
        cost = (total_in * price_in / 1000) + (total_out * price_out / 1000)

        results.append(
            ComponentCost(
                component=component,
                call_count=call_count,
                input_tokens=total_in,
                output_tokens=total_out,
                cost_usd=cost,
            )
        )

    return results


def total_cost(components: list[ComponentCost]) -> float:
    """Sum total estimated cost."""
    return sum(c.cost_usd for c in components)
