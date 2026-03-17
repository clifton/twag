"""LLM client infrastructure: provider dispatch, retry logic, JSON parsing."""

import json
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any

from anthropic import Anthropic

from twag.auth import get_api_key
from twag.config import load_config

# --- Cost-per-token pricing (USD per token) ---
# Input/output prices per 1M tokens converted to per-token
COST_PER_TOKEN: dict[str, dict[str, float]] = {
    # Anthropic models
    "claude-sonnet-4-20250514": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-haiku-4-20250414": {"input": 0.80 / 1_000_000, "output": 4.0 / 1_000_000},
    "claude-3-5-sonnet-20241022": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-3-5-haiku-20241022": {"input": 0.80 / 1_000_000, "output": 4.0 / 1_000_000},
    # Gemini models
    "gemini-2.5-flash": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gemini-2.5-pro": {"input": 1.25 / 1_000_000, "output": 10.0 / 1_000_000},
    "gemini-2.0-flash": {"input": 0.10 / 1_000_000, "output": 0.40 / 1_000_000},
    "gemini-3.1-pro": {"input": 1.25 / 1_000_000, "output": 10.0 / 1_000_000},
}

# --- Usage accumulator (thread-safe) ---
_usage_lock = threading.Lock()
_usage_events: list[dict[str, Any]] = []


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a call using the pricing table."""
    pricing = COST_PER_TOKEN.get(model)
    if not pricing:
        # Try prefix match for model variants
        for key, p in COST_PER_TOKEN.items():
            if model.startswith(key.rsplit("-", 1)[0]):
                pricing = p
                break
    if not pricing:
        return 0.0
    return input_tokens * pricing["input"] + output_tokens * pricing["output"]


def _record_usage(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    component: str | None,
) -> None:
    """Append a usage event to the module-level accumulator."""
    if component is None:
        return
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": component,
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": _estimate_cost(model, input_tokens, output_tokens),
    }
    with _usage_lock:
        _usage_events.append(event)


def flush_usage_events() -> list[dict[str, Any]]:
    """Drain and return all accumulated usage events."""
    with _usage_lock:
        events = list(_usage_events)
        _usage_events.clear()
    return events


def get_anthropic_client() -> Anthropic:
    """Get an Anthropic client."""
    return Anthropic(api_key=get_api_key("ANTHROPIC_API_KEY"))


def get_gemini_client():
    """Get a Gemini client using the new google.genai SDK."""
    from google import genai

    return genai.Client(api_key=get_api_key("GEMINI_API_KEY"))


def _extract_anthropic_text(content_blocks: list[Any]) -> str:
    """Return first textual content block from Anthropic response."""
    for block in content_blocks:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            return text
    return ""


def _call_anthropic(model: str, prompt: str, max_tokens: int = 2048, component: str | None = None) -> str:
    """Call Anthropic API and return text response."""
    client = get_anthropic_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    usage = response.usage
    _record_usage("anthropic", model, usage.input_tokens, usage.output_tokens, component)
    return _extract_anthropic_text(response.content)


def _call_gemini(
    model: str,
    prompt: str,
    max_tokens: int = 2048,
    reasoning: str | None = None,
    component: str | None = None,
) -> str:
    """Call Gemini API and return text response."""
    from google.genai import types

    client = get_gemini_client()

    config_kwargs: dict = {"max_output_tokens": max_tokens}

    # Add thinking config if reasoning is specified
    if reasoning:
        # Gemini 3+ uses thinking_level (string: "low", "medium", "high")
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=reasoning)  # ty: ignore[invalid-argument-type]

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    metadata = getattr(response, "usage_metadata", None)
    if metadata:
        _record_usage(
            "gemini",
            model,
            getattr(metadata, "prompt_token_count", 0) or 0,
            getattr(metadata, "candidates_token_count", 0) or 0,
            component,
        )
    return response.text


def _call_anthropic_vision(
    model: str, image_url: str, prompt: str, max_tokens: int = 1024, component: str | None = None
) -> str:
    """Call Anthropic API with image and return text response."""
    client = get_anthropic_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "url",
                            "url": image_url,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )
    usage = response.usage
    _record_usage("anthropic", model, usage.input_tokens, usage.output_tokens, component)
    return _extract_anthropic_text(response.content)


def _call_gemini_vision(
    model: str, image_url: str, prompt: str, max_tokens: int = 1024, component: str | None = None
) -> str:
    """Call Gemini API with image and return text response."""
    import httpx
    from google.genai import types

    client = get_gemini_client()

    # Fetch image
    resp = httpx.get(image_url, timeout=30)
    resp.raise_for_status()
    image_data = resp.content
    mime_type = resp.headers.get("content-type", "image/jpeg")

    # Create image part using new SDK
    image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)

    response = client.models.generate_content(
        model=model,
        contents=[prompt, image_part],
        config=types.GenerateContentConfig(
            max_output_tokens=max_tokens,
        ),
    )
    metadata = getattr(response, "usage_metadata", None)
    if metadata:
        _record_usage(
            "gemini",
            model,
            getattr(metadata, "prompt_token_count", 0) or 0,
            getattr(metadata, "candidates_token_count", 0) or 0,
            component,
        )
    return response.text


def _call_llm(
    provider: str,
    model: str,
    prompt: str,
    max_tokens: int = 2048,
    reasoning: str | None = None,
    component: str | None = None,
) -> str:
    """Call LLM based on provider."""

    def _invoke() -> str:
        if provider == "gemini":
            return _call_gemini(model, prompt, max_tokens, reasoning=reasoning, component=component)
        return _call_anthropic(model, prompt, max_tokens, component=component)

    return _with_retry(_invoke)


def _call_llm_vision(
    provider: str,
    model: str,
    image_url: str,
    prompt: str,
    max_tokens: int = 1024,
    component: str | None = None,
) -> str:
    """Call LLM with vision based on provider."""

    def _invoke() -> str:
        if provider == "gemini":
            return _call_gemini_vision(model, image_url, prompt, max_tokens, component=component)
        return _call_anthropic_vision(model, image_url, prompt, max_tokens, component=component)

    return _with_retry(_invoke)


def _with_retry(fn):
    config = load_config()
    retries = config.get("llm", {}).get("retry_max_attempts", 4)
    base_delay = config.get("llm", {}).get("retry_base_seconds", 1.0)
    max_delay = config.get("llm", {}).get("retry_max_seconds", 20.0)
    jitter = config.get("llm", {}).get("retry_jitter", 0.3)

    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            attempt += 1
            msg = str(exc).lower()
            if "not set" in msg and "api" in msg:
                raise
            if retries and attempt >= retries:
                raise

            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            if jitter:
                delay = max(0.0, delay * (1 + random.uniform(-jitter, jitter)))
            time.sleep(delay)


def _parse_json_response(text: str) -> dict[str, Any] | list[dict[str, Any]]:
    """Extract and parse JSON from model response."""
    # Try to find JSON in the response
    text = text.strip()

    # Remove markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (code fence markers)
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the start of JSON
    start_idx = -1
    for i, c in enumerate(text):
        if c in "[{":
            start_idx = i
            break

    if start_idx >= 0:
        json_text = text[start_idx:]
        # Try direct parse
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass

        # Try to fix truncated JSON array by closing it
        if json_text.startswith("["):
            # Find last complete object
            try:
                # Try adding closing bracket
                fixed = json_text.rstrip().rstrip(",") + "]"
                return json.loads(fixed)
            except json.JSONDecodeError:
                # Try to find last complete object and close there
                last_brace = json_text.rfind("}")
                if last_brace > 0:
                    try:
                        fixed = json_text[: last_brace + 1] + "]"
                        return json.loads(fixed)
                    except json.JSONDecodeError:
                        pass

        # Try to fix truncated JSON object
        if json_text.startswith("{"):
            try:
                fixed = json_text.rstrip().rstrip(",") + "}"
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

    raise ValueError(f"Could not parse JSON from: {text[:200]}")
