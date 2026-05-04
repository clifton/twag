"""LLM client infrastructure: provider dispatch, retry logic, JSON parsing."""

import json
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

from anthropic import Anthropic

from twag.auth import get_api_key
from twag.config import load_config
from twag.db.inference import begin_llm_usage_attempt, complete_llm_usage_attempt

_T = TypeVar("_T")

_NON_RETRYABLE_ERROR_PATTERNS = (
    "api key",
    "authentication",
    "unauthorized",
    "401",
    "403",
    "400",
    "bad request",
    "context length",
    "maximum context",
    "max tokens",
)

_RETRYABLE_ERROR_PATTERNS = (
    "429",
    "rate limit",
    "too many requests",
    "overloaded",
    "temporarily",
    "try again",
    "502",
    "503",
    "504",
    "connection reset",
    "connection aborted",
    "server disconnected",
    "remote protocol",
)


def get_anthropic_client() -> Anthropic:
    """Get an Anthropic client."""
    return Anthropic(api_key=get_api_key("ANTHROPIC_API_KEY"))


def get_gemini_client():
    """Get a Gemini client using the new google.genai SDK."""
    from google import genai

    return genai.Client(api_key=get_api_key("GEMINI_API_KEY"))


def get_deepseek_api_key() -> str:
    """Get a DeepSeek API key."""
    return get_api_key("DEEPSEEK_API_KEY")


def _extract_anthropic_text(content_blocks: list[Any]) -> str:
    """Return first textual content block from Anthropic response."""
    for block in content_blocks:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            return text
    return ""


def _usage_get(usage: Any, *names: str) -> int:
    """Read a token count from dict-like or SDK-object usage metadata."""
    if usage is None:
        return 0
    for name in names:
        if isinstance(usage, dict):
            value = usage.get(name)
        else:
            value = getattr(usage, name, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
    return 0


def _usage_to_dict(usage: Any) -> dict[str, Any]:
    """Best-effort JSON-safe copy of provider usage metadata."""
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    model_dump = getattr(usage, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump(mode="json")
        except TypeError:
            return model_dump()
    result: dict[str, Any] = {}
    for name in (
        "prompt_token_count",
        "candidates_token_count",
        "cached_content_token_count",
        "thoughts_token_count",
        "total_token_count",
        "input_tokens",
        "output_tokens",
    ):
        value = getattr(usage, name, None)
        if value is not None:
            result[name] = value
    return result


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return chain


def _is_timeout_error(exc: BaseException) -> bool:
    for item in _exception_chain(exc):
        if isinstance(item, TimeoutError):
            return True
        class_name = item.__class__.__name__.lower()
        if "timeout" in class_name:
            return True
        msg = str(item).lower()
        if "timed out" in msg or "timeout" in msg:
            return True
    return False


def _should_retry_llm_error(exc: BaseException) -> bool:
    if _is_timeout_error(exc):
        return False

    msg = " ".join(str(item).lower() for item in _exception_chain(exc))
    if "not set" in msg and "api" in msg:
        return False
    if any(pattern in msg for pattern in _NON_RETRYABLE_ERROR_PATTERNS):
        return False
    return any(pattern in msg for pattern in _RETRYABLE_ERROR_PATTERNS)


def _record_llm_usage(
    *,
    attempt_id: int | None = None,
    component: str,
    provider: str,
    model: str,
    prompt: str,
    max_tokens: int,
    latency_seconds: float | None,
    success: bool,
    is_vision: bool = False,
    response_text: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    reasoning_tokens: int = 0,
    cached_input_tokens: int = 0,
    total_tokens: int = 0,
    error: Exception | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record provider usage without allowing logging failures to affect scoring."""
    complete_llm_usage_attempt(
        attempt_id,
        component=component,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cached_input_tokens=cached_input_tokens,
        total_tokens=total_tokens,
        max_tokens=max_tokens,
        latency_seconds=latency_seconds,
        success=success,
        error_type=type(error).__name__ if error else None,
        error_message=str(error) if error else None,
        prompt_chars=len(prompt),
        response_chars=len(response_text or ""),
        is_vision=is_vision,
        metadata=metadata,
    )


def _begin_llm_usage(
    *,
    component: str,
    provider: str,
    model: str,
    prompt: str,
    max_tokens: int,
    is_vision: bool = False,
    metadata: dict[str, Any] | None = None,
) -> int | None:
    """Record that a provider request is about to be sent."""
    return begin_llm_usage_attempt(
        component=component,
        provider=provider,
        model=model,
        max_tokens=max_tokens,
        prompt_chars=len(prompt),
        is_vision=is_vision,
        metadata=metadata,
    )


def _call_anthropic(model: str, prompt: str, max_tokens: int = 2048, component: str = "unknown") -> str:
    """Call Anthropic API and return text response."""
    from twag.metrics import get_collector

    m = get_collector()
    m.inc("scorer.anthropic.calls")
    t0 = time.monotonic()
    attempt_id: int | None = None
    try:
        client = get_anthropic_client()
        attempt_id = _begin_llm_usage(
            component=component,
            provider="anthropic",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
        )
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _extract_anthropic_text(response.content)
        latency = time.monotonic() - t0
        m.observe("scorer.anthropic.latency_seconds", latency)
        input_tokens = 0
        output_tokens = 0
        usage_metadata: dict[str, Any] = {}
        if hasattr(response, "usage") and response.usage:
            input_tokens = _usage_get(response.usage, "input_tokens")
            output_tokens = _usage_get(response.usage, "output_tokens")
            usage_metadata = _usage_to_dict(response.usage)
            m.inc("scorer.anthropic.input_tokens", input_tokens)
            m.inc("scorer.anthropic.output_tokens", output_tokens)
        _record_llm_usage(
            attempt_id=attempt_id,
            component=component,
            provider="anthropic",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            latency_seconds=latency,
            success=True,
            response_text=result,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            metadata={"usage": usage_metadata} if usage_metadata else None,
        )
        return result
    except Exception as exc:
        m.inc("scorer.anthropic.errors")
        _record_llm_usage(
            attempt_id=attempt_id,
            component=component,
            provider="anthropic",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            latency_seconds=time.monotonic() - t0,
            success=False,
            error=exc,
        )
        raise


def _call_gemini(
    model: str,
    prompt: str,
    max_tokens: int = 2048,
    reasoning: str | None = None,
    component: str = "unknown",
) -> str:
    """Call Gemini API and return text response."""
    from google.genai import types

    from twag.metrics import get_collector

    m = get_collector()
    m.inc("scorer.gemini.calls")
    t0 = time.monotonic()
    attempt_id: int | None = None
    try:
        client = get_gemini_client()

        config_kwargs: dict = {"max_output_tokens": max_tokens}

        # Add thinking config if reasoning is specified
        if reasoning:
            # Gemini 3+ uses thinking_level (string: "low", "medium", "high")
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=reasoning)  # ty: ignore[invalid-argument-type]

        attempt_id = _begin_llm_usage(
            component=component,
            provider="gemini",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
        )
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        latency = time.monotonic() - t0
        m.observe("scorer.gemini.latency_seconds", latency)

        usage = getattr(response, "usage_metadata", None)
        input_tokens = _usage_get(usage, "prompt_token_count")
        output_tokens = _usage_get(usage, "candidates_token_count")
        cached_tokens = _usage_get(usage, "cached_content_token_count")
        reasoning_tokens = _usage_get(usage, "thoughts_token_count")
        total_tokens = _usage_get(usage, "total_token_count") or input_tokens + output_tokens + reasoning_tokens
        if input_tokens:
            m.inc("scorer.gemini.input_tokens", input_tokens)
        if output_tokens:
            m.inc("scorer.gemini.output_tokens", output_tokens)
        if reasoning_tokens:
            m.inc("scorer.gemini.reasoning_tokens", reasoning_tokens)

        result = response.text or ""
        usage_metadata = _usage_to_dict(usage)
        _record_llm_usage(
            attempt_id=attempt_id,
            component=component,
            provider="gemini",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            latency_seconds=latency,
            success=True,
            response_text=result,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_tokens,
            total_tokens=total_tokens,
            metadata={"usage": usage_metadata} if usage_metadata else None,
        )
        return result
    except Exception as exc:
        m.inc("scorer.gemini.errors")
        _record_llm_usage(
            attempt_id=attempt_id,
            component=component,
            provider="gemini",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            latency_seconds=time.monotonic() - t0,
            success=False,
            error=exc,
        )
        raise


def _normalize_deepseek_reasoning(reasoning: str | None) -> str | None:
    """Map twag reasoning labels onto DeepSeek's documented effort values."""
    if not reasoning:
        return None
    normalized = reasoning.strip().lower()
    if normalized in {"disabled", "off", "none"}:
        return None
    if normalized in {"low", "medium", "high"}:
        return normalized
    if normalized in {"xhigh", "max"}:
        return "max"
    return normalized


def _configured_llm_timeout_seconds(default: float = 120.0) -> float:
    """Return the configured per-request LLM timeout in seconds."""
    try:
        value = float(load_config().get("llm", {}).get("request_timeout_seconds", default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _call_deepseek(
    model: str,
    prompt: str,
    max_tokens: int = 2048,
    reasoning: str | None = None,
    component: str = "unknown",
    json_schema: dict[str, Any] | None = None,
    json_tool_name: str = "emit_json",
) -> str:
    """Call DeepSeek's OpenAI-compatible Chat Completions API and return text."""
    import httpx

    from twag.metrics import get_collector

    m = get_collector()
    m.inc("scorer.deepseek.calls")
    t0 = time.monotonic()
    attempt_id: int | None = None
    usage: dict[str, Any] = {}
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    reasoning_tokens = 0
    cached_tokens = 0
    try:
        effort = _normalize_deepseek_reasoning(reasoning)
        request_timeout = _configured_llm_timeout_seconds()
        api_key = get_deepseek_api_key()
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "stream": False,
            "thinking": {"type": "enabled" if effort else "disabled"},
        }
        if effort:
            payload["reasoning_effort"] = effort
        use_strict_tool = bool(json_schema and not effort)
        use_json_object = bool(json_schema and effort)
        if use_strict_tool:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": json_tool_name,
                        "description": "Return the requested structured analysis.",
                        "strict": True,
                        "parameters": json_schema,
                    },
                },
            ]
            payload["tool_choice"] = {"type": "function", "function": {"name": json_tool_name}}
        elif use_json_object:
            # DeepSeek's strict tool mode currently rejects thinking/reasoning
            # mode. JSON mode is the supported structured-output path when
            # preserving configured reasoning effort.
            payload["response_format"] = {"type": "json_object"}

        attempt_id = _begin_llm_usage(
            component=component,
            provider="deepseek",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            metadata={
                "thinking": payload["thinking"],
                "reasoning_effort": effort,
                "structured_output": bool(json_schema),
                "structured_output_mode": "strict_tool"
                if use_strict_tool
                else "json_object"
                if use_json_object
                else None,
                "json_tool_name": json_tool_name if json_schema else None,
                "request_timeout_seconds": request_timeout,
            },
        )
        response = httpx.post(
            "https://api.deepseek.com/beta/chat/completions"
            if use_strict_tool
            else "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=request_timeout,
        )
        try:
            response.raise_for_status()
        except Exception as exc:
            body = response.text[:1000]
            raise RuntimeError(f"DeepSeek HTTP {response.status_code}: {body}") from exc
        data = response.json()
        latency = time.monotonic() - t0
        m.observe("scorer.deepseek.latency_seconds", latency)

        if isinstance(data, dict):
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            if isinstance(usage, dict):
                input_tokens = _usage_get(usage, "prompt_tokens")
                output_tokens = _usage_get(usage, "completion_tokens")
                total_tokens = _usage_get(usage, "total_tokens") or input_tokens + output_tokens
                cached_tokens = _usage_get(usage, "prompt_cache_hit_tokens", "cache_hit_tokens")
                completion_details = usage.get("completion_tokens_details")
                if isinstance(completion_details, dict):
                    reasoning_tokens = _usage_get(completion_details, "reasoning_tokens")
                m.inc("scorer.deepseek.input_tokens", input_tokens)
                m.inc("scorer.deepseek.output_tokens", output_tokens)

            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    message = first_choice.get("message")
                    if isinstance(message, dict):
                        tool_calls = message.get("tool_calls")
                        if use_strict_tool and isinstance(tool_calls, list) and tool_calls:
                            tool_call = tool_calls[0]
                            if isinstance(tool_call, dict):
                                function_call = tool_call.get("function")
                                if isinstance(function_call, dict):
                                    arguments = function_call.get("arguments")
                                    if isinstance(arguments, str):
                                        _record_llm_usage(
                                            attempt_id=attempt_id,
                                            component=component,
                                            provider="deepseek",
                                            model=model,
                                            prompt=prompt,
                                            max_tokens=max_tokens,
                                            latency_seconds=latency,
                                            success=True,
                                            response_text=arguments,
                                            input_tokens=input_tokens,
                                            output_tokens=output_tokens,
                                            reasoning_tokens=reasoning_tokens,
                                            cached_input_tokens=cached_tokens,
                                            total_tokens=total_tokens,
                                            metadata={"usage": usage, "tool_call": function_call} if usage else None,
                                        )
                                        return arguments

                        content = message.get("content")
                        if isinstance(content, str) and content.strip():
                            _record_llm_usage(
                                attempt_id=attempt_id,
                                component=component,
                                provider="deepseek",
                                model=model,
                                prompt=prompt,
                                max_tokens=max_tokens,
                                latency_seconds=latency,
                                success=True,
                                response_text=content,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                reasoning_tokens=reasoning_tokens,
                                cached_input_tokens=cached_tokens,
                                total_tokens=total_tokens,
                                metadata={"usage": usage} if usage else None,
                            )
                            return content

        raise RuntimeError("DeepSeek response did not contain message content")
    except Exception as exc:
        m.inc("scorer.deepseek.errors")
        _record_llm_usage(
            attempt_id=attempt_id,
            component=component,
            provider="deepseek",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            latency_seconds=time.monotonic() - t0,
            success=False,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_tokens,
            total_tokens=total_tokens,
            error=exc,
            metadata={"usage": usage} if usage else None,
        )
        raise


def _call_anthropic_vision(
    model: str,
    image_url: str,
    prompt: str,
    max_tokens: int = 1024,
    component: str = "vision",
) -> str:
    """Call Anthropic API with image and return text response."""
    t0 = time.monotonic()
    attempt_id: int | None = None
    try:
        client = get_anthropic_client()
        attempt_id = _begin_llm_usage(
            component=component,
            provider="anthropic",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            is_vision=True,
            metadata={"image_url": image_url},
        )
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
        result = _extract_anthropic_text(response.content)
        usage = getattr(response, "usage", None)
        input_tokens = _usage_get(usage, "input_tokens")
        output_tokens = _usage_get(usage, "output_tokens")
        _record_llm_usage(
            attempt_id=attempt_id,
            component=component,
            provider="anthropic",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            latency_seconds=time.monotonic() - t0,
            success=True,
            is_vision=True,
            response_text=result,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            metadata={"usage": _usage_to_dict(usage)} if usage else None,
        )
        return result
    except Exception as exc:
        _record_llm_usage(
            attempt_id=attempt_id,
            component=component,
            provider="anthropic",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            latency_seconds=time.monotonic() - t0,
            success=False,
            is_vision=True,
            error=exc,
        )
        raise


def _call_gemini_vision(
    model: str,
    image_url: str,
    prompt: str,
    max_tokens: int = 1024,
    component: str = "vision",
) -> str:
    """Call Gemini API with image and return text response."""
    import httpx
    from google.genai import types

    t0 = time.monotonic()
    attempt_id: int | None = None
    try:
        client = get_gemini_client()

        # Fetch image
        resp = httpx.get(image_url, timeout=30)
        resp.raise_for_status()
        image_data = resp.content
        mime_type = resp.headers.get("content-type", "image/jpeg")

        # Create image part using new SDK
        image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)

        attempt_id = _begin_llm_usage(
            component=component,
            provider="gemini",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            is_vision=True,
            metadata={"image_url": image_url, "mime_type": mime_type},
        )
        response = client.models.generate_content(
            model=model,
            contents=[prompt, image_part],
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
            ),
        )
        result = response.text or ""
        usage = getattr(response, "usage_metadata", None)
        input_tokens = _usage_get(usage, "prompt_token_count")
        output_tokens = _usage_get(usage, "candidates_token_count")
        cached_tokens = _usage_get(usage, "cached_content_token_count")
        reasoning_tokens = _usage_get(usage, "thoughts_token_count")
        total_tokens = _usage_get(usage, "total_token_count") or input_tokens + output_tokens + reasoning_tokens
        _record_llm_usage(
            attempt_id=attempt_id,
            component=component,
            provider="gemini",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            latency_seconds=time.monotonic() - t0,
            success=True,
            is_vision=True,
            response_text=result,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_tokens,
            total_tokens=total_tokens,
            metadata={"usage": _usage_to_dict(usage), "mime_type": mime_type} if usage else {"mime_type": mime_type},
        )
        return result
    except Exception as exc:
        _record_llm_usage(
            attempt_id=attempt_id,
            component=component,
            provider="gemini",
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            latency_seconds=time.monotonic() - t0,
            success=False,
            is_vision=True,
            error=exc,
        )
        raise


def _call_llm(
    provider: str,
    model: str,
    prompt: str,
    max_tokens: int = 2048,
    reasoning: str | None = None,
    component: str = "unknown",
    json_schema: dict[str, Any] | None = None,
    json_tool_name: str = "emit_json",
) -> str:
    """Call LLM based on provider."""

    def _invoke() -> str:
        if provider == "gemini":
            return _call_gemini(model, prompt, max_tokens, reasoning=reasoning, component=component)
        if provider == "deepseek":
            return _call_deepseek(
                model,
                prompt,
                max_tokens,
                reasoning=reasoning,
                component=component,
                json_schema=json_schema,
                json_tool_name=json_tool_name,
            )
        if provider == "anthropic":
            return _call_anthropic(model, prompt, max_tokens, component=component)
        raise ValueError(f"Unsupported LLM provider: {provider}")

    return _with_retry(_invoke)


def _call_llm_vision(
    provider: str,
    model: str,
    image_url: str,
    prompt: str,
    max_tokens: int = 1024,
    component: str = "vision",
) -> str:
    """Call LLM with vision based on provider."""

    def _invoke() -> str:
        if provider == "gemini":
            return _call_gemini_vision(model, image_url, prompt, max_tokens, component=component)
        if provider == "anthropic":
            return _call_anthropic_vision(model, image_url, prompt, max_tokens, component=component)
        if provider == "deepseek":
            raise ValueError("DeepSeek provider does not support twag vision analysis; use gemini or anthropic")
        raise ValueError(f"Unsupported LLM provider: {provider}")

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
            if not _should_retry_llm_error(exc):
                m.inc("scorer.retry_suppressed")
                raise
            if retries and attempt >= retries:
                raise

            m.inc("scorer.retries")
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
