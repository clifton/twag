"""LLM client infrastructure: provider dispatch, retry logic, JSON parsing."""

import json
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

from anthropic import Anthropic

from twag.auth import get_api_key
from twag.config import load_config

_T = TypeVar("_T")


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


def _call_anthropic(model: str, prompt: str, max_tokens: int = 2048) -> str:
    """Call Anthropic API and return text response."""
    from twag import metrics

    labels = {"model": model}
    metrics.counter("scorer.anthropic.calls", labels=labels)
    t0 = time.monotonic()
    try:
        client = get_anthropic_client()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _extract_anthropic_text(response.content)
        metrics.histogram("scorer.anthropic.latency_seconds", time.monotonic() - t0, labels=labels)
        _record_anthropic_usage(response, labels=labels)
        return result
    except Exception:
        metrics.counter("scorer.anthropic.errors", labels=labels)
        raise


def _record_anthropic_usage(response: Any, *, labels: dict[str, str], kind: str = "") -> None:
    """Increment Anthropic input/output token counters from response.usage.

    ``kind`` is an optional prefix on the counter suffix — pass ``"vision_"`` to
    record into ``scorer.anthropic.vision_input_tokens`` / ``vision_output_tokens``.
    """
    from twag import metrics

    try:
        usage = getattr(response, "usage", None)
        if not usage:
            return
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        if input_tokens:
            metrics.counter(f"scorer.anthropic.{kind}input_tokens", value=input_tokens, labels=labels)
        if output_tokens:
            metrics.counter(f"scorer.anthropic.{kind}output_tokens", value=output_tokens, labels=labels)
    except Exception:
        return


def _record_gemini_usage(response: Any, *, labels: dict[str, str], kind: str = "") -> None:
    """Increment Gemini input/output token counters from response.usage_metadata.

    Wrapped in a defensive try/except so a malformed response can't trigger the
    outer error counter for an otherwise-successful call. ``kind`` lets callers
    record vision-specific counters by passing ``"vision_"``.
    """
    from twag import metrics

    try:
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        if input_tokens:
            metrics.counter(f"scorer.gemini.{kind}input_tokens", value=input_tokens, labels=labels)
        if output_tokens:
            metrics.counter(f"scorer.gemini.{kind}output_tokens", value=output_tokens, labels=labels)
    except Exception:
        return


def _call_gemini(model: str, prompt: str, max_tokens: int = 2048, reasoning: str | None = None) -> str:
    """Call Gemini API and return text response."""
    from google.genai import types

    from twag import metrics

    labels = {"model": model}
    metrics.counter("scorer.gemini.calls", labels=labels)
    t0 = time.monotonic()
    try:
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
        metrics.histogram("scorer.gemini.latency_seconds", time.monotonic() - t0, labels=labels)
        _record_gemini_usage(response, labels=labels)
        return response.text
    except Exception:
        metrics.counter("scorer.gemini.errors", labels=labels)
        raise


def _call_anthropic_vision(model: str, image_url: str, prompt: str, max_tokens: int = 1024) -> str:
    """Call Anthropic API with image and return text response."""
    from twag import metrics

    labels = {"model": model}
    metrics.counter("scorer.anthropic.vision_calls", labels=labels)
    t0 = time.monotonic()
    try:
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
                },
            ],
        )
        metrics.histogram("scorer.anthropic.vision_latency_seconds", time.monotonic() - t0, labels=labels)
        _record_anthropic_usage(response, labels=labels, kind="vision_")
        return _extract_anthropic_text(response.content)
    except Exception:
        metrics.counter("scorer.anthropic.vision_errors", labels=labels)
        raise


def _call_gemini_vision(model: str, image_url: str, prompt: str, max_tokens: int = 1024) -> str:
    """Call Gemini API with image and return text response."""
    import httpx
    from google.genai import types

    from twag import metrics

    labels = {"model": model}
    metrics.counter("scorer.gemini.vision_calls", labels=labels)
    t0 = time.monotonic()
    try:
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
        metrics.histogram("scorer.gemini.vision_latency_seconds", time.monotonic() - t0, labels=labels)
        _record_gemini_usage(response, labels=labels, kind="vision_")
        return response.text
    except Exception:
        metrics.counter("scorer.gemini.vision_errors", labels=labels)
        raise


def _call_llm(provider: str, model: str, prompt: str, max_tokens: int = 2048, reasoning: str | None = None) -> str:
    """Call LLM based on provider."""

    def _invoke() -> str:
        if provider == "gemini":
            return _call_gemini(model, prompt, max_tokens, reasoning=reasoning)
        return _call_anthropic(model, prompt, max_tokens)

    return _with_retry(_invoke)


def _call_llm_vision(provider: str, model: str, image_url: str, prompt: str, max_tokens: int = 1024) -> str:
    """Call LLM with vision based on provider."""

    def _invoke() -> str:
        if provider == "gemini":
            return _call_gemini_vision(model, image_url, prompt, max_tokens)
        return _call_anthropic_vision(model, image_url, prompt, max_tokens)

    return _with_retry(_invoke)


def _with_retry(fn: Callable[[], _T]) -> _T:
    from twag.metrics import get_collector

    m = get_collector()
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
            m.inc("scorer.retries")
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
