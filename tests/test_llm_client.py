"""Tests for LLM provider dispatch."""

import httpx
import pytest

from twag.scorer import llm_client


class _FakeDeepSeekResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        }


class _FakeDeepSeekToolResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "emit_enrichment",
                                    "arguments": '{"signal_tier":"high_signal","tickers":["TSLA"]}',
                                },
                            },
                        ],
                    },
                },
            ],
            "usage": {"prompt_tokens": 13, "completion_tokens": 9},
        }


class _FakeDeepSeekJsonResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [{"message": {"content": '{"signal_tier":"high_signal","tickers":["TSLA"]}'}}],
            "usage": {"prompt_tokens": 17, "completion_tokens": 11},
        }


def test_call_deepseek_disables_thinking_by_default(monkeypatch) -> None:
    seen: dict = {}
    started: dict = {}
    completed: dict = {}

    def _fake_post(url, *, headers, json, timeout):
        seen["url"] = url
        seen["headers"] = headers
        seen["json"] = json
        seen["timeout"] = timeout
        return _FakeDeepSeekResponse()

    monkeypatch.setattr(llm_client, "get_deepseek_api_key", lambda: "test-key")
    monkeypatch.setattr(llm_client, "load_config", lambda: {"llm": {}})
    monkeypatch.setattr(httpx, "post", _fake_post)
    monkeypatch.setattr(
        llm_client,
        "begin_llm_usage_attempt",
        lambda **kwargs: started.update(kwargs) or 123,
    )
    monkeypatch.setattr(
        llm_client,
        "complete_llm_usage_attempt",
        lambda attempt_id, **kwargs: completed.update({"attempt_id": attempt_id, **kwargs}),
    )

    result = llm_client._call_deepseek("deepseek-v4-pro", "hello", max_tokens=12)

    assert result == "ok"
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert seen["json"]["model"] == "deepseek-v4-pro"
    assert seen["json"]["messages"] == [{"role": "user", "content": "hello"}]
    assert seen["json"]["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in seen["json"]
    assert seen["json"]["max_tokens"] == 12
    assert seen["timeout"] == 120
    assert started["component"] == "unknown"
    assert started["provider"] == "deepseek"
    assert started["prompt_chars"] == 5
    assert completed["attempt_id"] == 123
    assert completed["component"] == "unknown"
    assert completed["provider"] == "deepseek"
    assert completed["input_tokens"] == 11
    assert completed["output_tokens"] == 7
    assert completed["success"] is True


def test_call_deepseek_uses_strict_tool_schema(monkeypatch) -> None:
    seen: dict = {}
    completed: dict = {}
    schema = {
        "type": "object",
        "properties": {"signal_tier": {"type": "string"}, "tickers": {"type": "array", "items": {"type": "string"}}},
        "required": ["signal_tier", "tickers"],
        "additionalProperties": False,
    }

    def _fake_post(url, *, headers, json, timeout):
        seen["url"] = url
        seen["json"] = json
        seen["timeout"] = timeout
        return _FakeDeepSeekToolResponse()

    monkeypatch.setattr(llm_client, "get_deepseek_api_key", lambda: "test-key")
    monkeypatch.setattr(llm_client, "load_config", lambda: {"llm": {"request_timeout_seconds": 45}})
    monkeypatch.setattr(httpx, "post", _fake_post)
    monkeypatch.setattr(llm_client, "begin_llm_usage_attempt", lambda **kwargs: 123)
    monkeypatch.setattr(
        llm_client,
        "complete_llm_usage_attempt",
        lambda attempt_id, **kwargs: completed.update({"attempt_id": attempt_id, **kwargs}),
    )

    result = llm_client._call_deepseek(
        "deepseek-v4-pro",
        "return json",
        max_tokens=32,
        json_schema=schema,
        json_tool_name="emit_enrichment",
    )

    assert result == '{"signal_tier":"high_signal","tickers":["TSLA"]}'
    assert seen["url"] == "https://api.deepseek.com/beta/chat/completions"
    assert seen["json"]["tools"][0]["function"]["strict"] is True
    assert seen["json"]["tools"][0]["function"]["parameters"] == schema
    assert seen["json"]["tool_choice"] == {"type": "function", "function": {"name": "emit_enrichment"}}
    assert seen["timeout"] == 45
    assert completed["attempt_id"] == 123
    assert completed["response_chars"] == len(result)
    assert completed["success"] is True


def test_call_deepseek_uses_json_mode_for_schema_with_reasoning(monkeypatch) -> None:
    seen: dict = {}
    schema = {
        "type": "object",
        "properties": {"signal_tier": {"type": "string"}, "tickers": {"type": "array", "items": {"type": "string"}}},
        "required": ["signal_tier", "tickers"],
        "additionalProperties": False,
    }

    def _fake_post(url, *, headers, json, timeout):
        seen["url"] = url
        seen["json"] = json
        return _FakeDeepSeekJsonResponse()

    monkeypatch.setattr(llm_client, "get_deepseek_api_key", lambda: "test-key")
    monkeypatch.setattr(llm_client, "load_config", lambda: {"llm": {}})
    monkeypatch.setattr(httpx, "post", _fake_post)
    monkeypatch.setattr(llm_client, "begin_llm_usage_attempt", lambda **kwargs: 123)
    monkeypatch.setattr(llm_client, "complete_llm_usage_attempt", lambda attempt_id, **kwargs: None)

    result = llm_client._call_deepseek(
        "deepseek-v4-pro",
        "return json",
        max_tokens=32,
        reasoning="high",
        json_schema=schema,
        json_tool_name="emit_enrichment",
    )

    assert result == '{"signal_tier":"high_signal","tickers":["TSLA"]}'
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert "tools" not in seen["json"]
    assert "tool_choice" not in seen["json"]
    assert seen["json"]["response_format"] == {"type": "json_object"}
    assert seen["json"]["thinking"] == {"type": "enabled"}
    assert seen["json"]["reasoning_effort"] == "high"


def test_call_deepseek_treats_low_reasoning_as_non_thinking(monkeypatch) -> None:
    seen: dict = {}
    schema = {
        "type": "object",
        "properties": {"signal_tier": {"type": "string"}, "tickers": {"type": "array", "items": {"type": "string"}}},
        "required": ["signal_tier", "tickers"],
        "additionalProperties": False,
    }

    def _fake_post(url, *, headers, json, timeout):
        seen["url"] = url
        seen["json"] = json
        return _FakeDeepSeekToolResponse()

    monkeypatch.setattr(llm_client, "get_deepseek_api_key", lambda: "test-key")
    monkeypatch.setattr(llm_client, "load_config", lambda: {"llm": {}})
    monkeypatch.setattr(httpx, "post", _fake_post)
    monkeypatch.setattr(llm_client, "begin_llm_usage_attempt", lambda **kwargs: 123)
    monkeypatch.setattr(llm_client, "complete_llm_usage_attempt", lambda attempt_id, **kwargs: None)

    result = llm_client._call_deepseek(
        "deepseek-v4-pro",
        "return json",
        max_tokens=32,
        reasoning="low",
        json_schema=schema,
        json_tool_name="emit_enrichment",
    )

    assert result == '{"signal_tier":"high_signal","tickers":["TSLA"]}'
    assert seen["url"] == "https://api.deepseek.com/beta/chat/completions"
    assert seen["json"]["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in seen["json"]
    assert seen["json"]["tools"][0]["function"]["strict"] is True


@pytest.mark.parametrize(
    ("reasoning", "expected"),
    [
        ("low", None),
        ("medium", "high"),
        ("high", "high"),
        ("xhigh", "max"),
        ("max", "max"),
    ],
)
def test_deepseek_reasoning_mapping(reasoning: str, expected: str) -> None:
    assert llm_client._normalize_deepseek_reasoning(reasoning) == expected


def test_deepseek_reasoning_can_be_disabled() -> None:
    assert llm_client._normalize_deepseek_reasoning("disabled") is None


def test_call_llm_rejects_unknown_provider(monkeypatch) -> None:
    monkeypatch.setattr(llm_client, "_with_retry", lambda fn: fn())

    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        llm_client._call_llm("bogus", "model", "prompt")


def test_call_llm_vision_rejects_deepseek(monkeypatch) -> None:
    monkeypatch.setattr(llm_client, "_with_retry", lambda fn: fn())

    with pytest.raises(ValueError, match="does not support twag vision"):
        llm_client._call_llm_vision("deepseek", "deepseek-v4-pro", "https://example.com/image.png", "prompt")


def test_with_retry_does_not_retry_timeouts(monkeypatch) -> None:
    calls = 0

    monkeypatch.setattr(
        llm_client,
        "load_config",
        lambda: {"llm": {"retry_max_attempts": 4, "retry_base_seconds": 0, "retry_jitter": 0}},
    )

    def _timeout():
        nonlocal calls
        calls += 1
        raise TimeoutError("request timed out")

    with pytest.raises(TimeoutError):
        llm_client._with_retry(_timeout)

    assert calls == 1


def test_with_retry_retries_transient_rate_limits(monkeypatch) -> None:
    calls = 0

    monkeypatch.setattr(
        llm_client,
        "load_config",
        lambda: {"llm": {"retry_max_attempts": 4, "retry_base_seconds": 0, "retry_jitter": 0}},
    )

    def _rate_limit_then_ok():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("429 rate limit")
        return "ok"

    assert llm_client._with_retry(_rate_limit_then_ok) == "ok"
    assert calls == 2
