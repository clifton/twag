"""Cost attribution estimator for twag.

Translates locally-tracked metrics (token counters per LLM provider, call counts)
into a per-component USD estimate. Pricing is configurable via the PRICING table
or a user-supplied JSON file (default: ``$XDG_CONFIG_HOME/twag/pricing.json``,
i.e. ``~/.config/twag/pricing.json``).

Estimates are advisory. Token counts come from the LLM SDKs' usage metadata when
available; calls without usage data are not priced. Non-LLM components (fetcher,
pipeline compute, web) are listed at $0 with an explanatory note.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import APP_NAME, get_xdg_config_home

if TYPE_CHECKING:
    import os

# (provider, model_substring) -> (input_per_million_usd, output_per_million_usd)
# Substring matching lets a single entry cover related model variants, and the
# longest matching substring wins.
PRICING: dict[tuple[str, str], tuple[float, float]] = {
    # Gemini (USD per 1M tokens; published rates as of early 2026)
    ("gemini", "gemini-3-pro"): (3.50, 21.00),
    ("gemini", "gemini-3-flash"): (0.30, 2.50),
    ("gemini", "gemini-3.1-pro"): (3.50, 21.00),
    ("gemini", "gemini-3.1-flash"): (0.30, 2.50),
    ("gemini", "gemini-2.5-pro"): (1.25, 10.00),
    ("gemini", "gemini-2.5-flash"): (0.075, 0.30),
    ("gemini", "gemini-2.0-flash"): (0.075, 0.30),
    ("gemini", "gemini"): (0.30, 2.50),  # generic fallback
    # Anthropic
    ("anthropic", "claude-opus-4-7"): (15.00, 75.00),
    ("anthropic", "claude-opus-4-6"): (15.00, 75.00),
    ("anthropic", "claude-opus-4"): (15.00, 75.00),
    ("anthropic", "claude-sonnet-4-6"): (3.00, 15.00),
    ("anthropic", "claude-sonnet-4"): (3.00, 15.00),
    ("anthropic", "claude-haiku-4-5"): (1.00, 5.00),
    ("anthropic", "claude-haiku-4"): (1.00, 5.00),
    ("anthropic", "claude"): (3.00, 15.00),  # generic fallback
}


def default_pricing_path() -> Path:
    """Default location for a user pricing override file (XDG-compliant)."""
    return get_xdg_config_home() / APP_NAME / "pricing.json"


@dataclass
class Component:
    """A single component's cost attribution."""

    name: str
    usd_estimate: float = 0.0
    breakdown: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


def _user_pricing_path(override: str | os.PathLike[str] | None = None) -> Path:
    if override is not None:
        return Path(override)
    return default_pricing_path()


def load_pricing_overrides(path: str | os.PathLike[str] | None = None) -> dict[tuple[str, str], tuple[float, float]]:
    """Load pricing overrides from JSON file.

    Format::

        {
          "gemini": {
            "gemini-3-pro": {"input_per_million_usd": 3.5, "output_per_million_usd": 21.0}
          },
          "anthropic": {
            "claude-haiku-4-5": [1.0, 5.0]
          }
        }
    """
    p = _user_pricing_path(path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)

    out: dict[tuple[str, str], tuple[float, float]] = {}
    for provider, models in raw.items():
        if not isinstance(models, dict):
            continue
        for model, rates in models.items():
            if isinstance(rates, dict):
                in_rate = float(rates.get("input_per_million_usd", 0.0))
                out_rate = float(rates.get("output_per_million_usd", 0.0))
            elif isinstance(rates, (list, tuple)) and len(rates) == 2:
                in_rate = float(rates[0])
                out_rate = float(rates[1])
            else:
                continue
            out[(provider, model)] = (in_rate, out_rate)
    return out


def lookup_rate(
    provider: str,
    model: str,
    pricing: dict[tuple[str, str], tuple[float, float]] | None = None,
) -> tuple[float, float] | None:
    """Look up (input_rate, output_rate) per million tokens.

    Tries exact match first, then longest-substring match. Returns ``None`` if
    no entry covers the model.
    """
    table = dict(PRICING)
    if pricing:
        table.update(pricing)

    exact = table.get((provider, model))
    if exact is not None:
        return exact

    candidates = [(key, rate) for key, rate in table.items() if key[0] == provider and key[1] in model]
    if not candidates:
        return None
    # Longest substring match wins
    candidates.sort(key=lambda item: len(item[0][1]), reverse=True)
    return candidates[0][1]


def derive_model_from_label(counter_name: str) -> tuple[str | None, str | None]:
    """Extract provider/model from a labeled counter name like
    ``scorer.gemini.input_tokens{model=gemini-3-pro}``.

    Returns ``(provider, model)`` where either may be ``None`` if not present.
    """
    provider: str | None = None
    model: str | None = None

    base = counter_name.split("{", 1)[0]
    parts = base.split(".")
    if len(parts) >= 2 and parts[0] == "scorer":
        provider = parts[1]

    if "{" in counter_name and counter_name.endswith("}"):
        labels_str = counter_name.split("{", 1)[1][:-1]
        for entry in labels_str.split(","):
            if "=" in entry:
                k, v = entry.split("=", 1)
                if k.strip() == "model":
                    model = v.strip()
                elif k.strip() == "provider" and provider is None:
                    provider = v.strip()
    return provider, model


def _aggregate_provider_tokens(counters: dict[str, float]) -> dict[str, dict[str, dict[str, float]]]:
    """Group token counts by provider and model.

    Returns ``{provider: {model_or_'unknown': {'input': X, 'output': Y, 'calls': N}}}``.
    Aggregates across both text and vision token counters.
    """
    by_provider: dict[str, dict[str, dict[str, float]]] = {}

    for name, value in counters.items():
        if not name.startswith("scorer."):
            continue

        provider, model = derive_model_from_label(name)
        if provider is None:
            continue

        base = name.split("{", 1)[0]
        suffix = base[len("scorer.") + len(provider) + 1 :] if base.startswith(f"scorer.{provider}.") else ""

        if suffix in ("input_tokens", "vision_input_tokens"):
            kind = "input"
        elif suffix in ("output_tokens", "vision_output_tokens"):
            kind = "output"
        elif suffix in ("calls", "vision_calls"):
            kind = "calls"
        else:
            continue

        bucket = by_provider.setdefault(provider, {}).setdefault(
            model or "unknown",
            {"input": 0.0, "output": 0.0, "calls": 0.0},
        )
        bucket[kind] = bucket.get(kind, 0.0) + value

    return by_provider


def _resolve_model_for_provider(provider: str, configured: dict[str, str]) -> str | None:
    """Pick a default model name for an unlabeled counter based on twag config."""
    triage = configured.get("triage")
    enrichment = configured.get("enrichment")
    if triage and ((provider == "gemini" and "gemini" in triage) or (provider == "anthropic" and "claude" in triage)):
        return triage
    if enrichment and (
        (provider == "gemini" and "gemini" in enrichment) or (provider == "anthropic" and "claude" in enrichment)
    ):
        return enrichment
    return triage or enrichment


def estimate_costs(
    snapshot: dict[str, Any],
    pricing: dict[tuple[str, str], tuple[float, float]] | None = None,
    configured_models: dict[str, str] | None = None,
) -> list[Component]:
    """Estimate costs by component from a metrics snapshot.

    ``snapshot`` should match ``MetricsCollector.snapshot()`` output: a dict with
    ``counters`` and ``histograms`` keys.

    ``configured_models`` maps role -> model name (e.g. ``{"triage": "gemini-3-flash-preview",
    "enrichment": "claude-opus-4-7"}``). Used as a fallback when token counters
    aren't model-labeled.
    """
    counters = snapshot.get("counters", {}) or {}
    histograms = snapshot.get("histograms", {}) or {}
    configured = configured_models or {}

    components: list[Component] = []

    # ── Scorer (LLM) components ────────────────────────────────────────────
    by_provider = _aggregate_provider_tokens(counters)
    for provider in sorted(by_provider):
        provider_total = 0.0
        provider_in_tokens = 0.0
        provider_out_tokens = 0.0
        provider_calls = 0.0
        provider_breakdown: dict[str, Any] = {"models": {}}
        provider_notes: list[str] = []

        for model_name, totals in by_provider[provider].items():
            in_tokens = totals.get("input", 0.0)
            out_tokens = totals.get("output", 0.0)
            calls = totals.get("calls", 0.0)

            effective_model = (
                model_name if model_name != "unknown" else _resolve_model_for_provider(provider, configured)
            )
            rate = lookup_rate(provider, effective_model, pricing) if effective_model else None

            if rate is None:
                cost = 0.0
                if in_tokens or out_tokens:
                    provider_notes.append(
                        f"no pricing entry for model='{effective_model or 'unknown'}'; counted tokens but priced at $0",
                    )
            else:
                in_rate, out_rate = rate
                cost = (in_tokens * in_rate + out_tokens * out_rate) / 1_000_000.0
                if model_name == "unknown" and effective_model:
                    provider_notes.append(f"used configured default model '{effective_model}' for unlabeled counters")

            provider_total += cost
            provider_in_tokens += in_tokens
            provider_out_tokens += out_tokens
            provider_calls += calls
            provider_breakdown["models"][model_name] = {
                "input_tokens": in_tokens,
                "output_tokens": out_tokens,
                "calls": calls,
                "usd_estimate": cost,
                "rate_used": effective_model,
            }

        provider_breakdown["calls"] = provider_calls
        provider_breakdown["input_tokens"] = provider_in_tokens
        provider_breakdown["output_tokens"] = provider_out_tokens
        components.append(
            Component(
                name=f"scorer:{provider}",
                usd_estimate=round(provider_total, 6),
                breakdown=provider_breakdown,
                notes="; ".join(provider_notes),
            ),
        )

    # If no scorer activity at all, still surface the component with $0
    if not by_provider:
        components.append(
            Component(
                name="scorer",
                usd_estimate=0.0,
                breakdown={"calls": 0, "input_tokens": 0, "output_tokens": 0},
                notes="no LLM activity recorded in this snapshot",
            ),
        )

    # ── Fetcher (bird CLI) — not priced ────────────────────────────────────
    fetcher_calls = sum(v for k, v in counters.items() if k.startswith("fetcher.") and k.endswith(".calls"))
    if fetcher_calls == 0:
        fetcher_calls = sum(v for k, v in counters.items() if k.startswith("fetcher."))
    components.append(
        Component(
            name="fetcher",
            usd_estimate=0.0,
            breakdown={"calls": fetcher_calls},
            notes="bird CLI is local; no API spend tracked",
        ),
    )

    # ── Pipeline compute — not priced ──────────────────────────────────────
    pipeline_total = 0.0
    for name, stats in histograms.items():
        if name.startswith("pipeline."):
            pipeline_total += stats.get("total", 0.0)
    components.append(
        Component(
            name="pipeline",
            usd_estimate=0.0,
            breakdown={"compute_seconds": round(pipeline_total, 3)},
            notes="local CPU only; not converted to USD",
        ),
    )

    # ── Web — not priced ───────────────────────────────────────────────────
    web_requests = counters.get("web.requests", 0.0)
    components.append(
        Component(
            name="web",
            usd_estimate=0.0,
            breakdown={"requests": web_requests},
            notes="self-hosted FastAPI; no API spend tracked",
        ),
    )

    return components


def total_usd(components: list[Component]) -> float:
    return round(sum(c.usd_estimate for c in components), 6)
