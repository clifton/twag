"""Tests for LLM provider dispatch."""

import httpx
import pytest

from twag.metrics import get_collector
from twag.scorer import llm_client
from twag.scorer.prompts import BATCH_TRIAGE_PROMPT
from twag.scorer.scoring import TRIAGE_BATCH_SCHEMA


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


def test_call_deepseek_uses_json_mode_for_high_reasoning_triage(monkeypatch) -> None:
    seen: dict = {}
    completed: dict = {}

    class TriageJsonResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [{"message": {"content": '{"items":[]}'}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 800,
                    "completion_tokens": 180,
                    "total_tokens": 980,
                    "completion_tokens_details": {"reasoning_tokens": 169},
                },
            }

    def fake_post(url, *, headers, json, timeout):
        seen.update(url=url, payload=json, timeout=timeout)
        return TriageJsonResponse()

    monkeypatch.setattr(llm_client, "get_deepseek_api_key", lambda: "test-key")
    monkeypatch.setattr(llm_client, "load_config", lambda: {"llm": {}})
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(llm_client, "begin_llm_usage_attempt", lambda **kwargs: 123)
    monkeypatch.setattr(
        llm_client,
        "complete_llm_usage_attempt",
        lambda attempt_id, **kwargs: completed.update({"attempt_id": attempt_id, **kwargs}),
    )

    result = llm_client._call_deepseek(
        "deepseek-v4-flash",
        BATCH_TRIAGE_PROMPT,
        max_tokens=4096,
        reasoning="high",
        component="triage",
        json_schema=TRIAGE_BATCH_SCHEMA,
        json_tool_name="emit_triage_batch",
    )

    assert result == '{"items":[]}'
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["payload"]["model"] == "deepseek-v4-flash"
    assert seen["payload"]["messages"] == [{"role": "user", "content": BATCH_TRIAGE_PROMPT}]
    assert seen["payload"]["max_tokens"] == 16_384
    assert seen["payload"]["thinking"] == {"type": "enabled"}
    assert seen["payload"]["reasoning_effort"] == "high"
    assert seen["payload"]["response_format"] == {"type": "json_object"}
    assert "tools" not in seen["payload"]
    assert "tool_choice" not in seen["payload"]
    assert completed["component"] == "triage"
    assert completed["model"] == "deepseek-v4-flash"
    assert completed["max_tokens"] == 16_384
    assert completed["reasoning_tokens"] == 169
    assert completed["success"] is True


def test_call_deepseek_empty_content_reports_budget_diagnostics(monkeypatch) -> None:
    completed: dict = {}

    class EmptyContentResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
                "usage": {
                    "prompt_tokens": 800,
                    "completion_tokens": 16_384,
                    "total_tokens": 17_184,
                    "completion_tokens_details": {"reasoning_tokens": 16_384},
                },
            }

    monkeypatch.setattr(llm_client, "get_deepseek_api_key", lambda: "test-key")
    monkeypatch.setattr(llm_client, "load_config", lambda: {"llm": {}})
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: EmptyContentResponse())
    monkeypatch.setattr(llm_client, "begin_llm_usage_attempt", lambda **kwargs: 123)
    monkeypatch.setattr(
        llm_client,
        "complete_llm_usage_attempt",
        lambda attempt_id, **kwargs: completed.update({"attempt_id": attempt_id, **kwargs}),
    )
    metrics = get_collector()
    empty_content_before = metrics.counter_value("scorer.deepseek.empty_content")

    with pytest.raises(
        RuntimeError,
        match=(
            r"finish_reason=length, completion_tokens=16384, "
            r"reasoning_tokens=16384, max_tokens=16384"
        ),
    ):
        llm_client._call_deepseek(
            "deepseek-v4-flash",
            BATCH_TRIAGE_PROMPT,
            max_tokens=4096,
            reasoning="high",
            component="triage",
            json_schema=TRIAGE_BATCH_SCHEMA,
        )

    assert metrics.counter_value("scorer.deepseek.empty_content") == empty_content_before + 1
    assert metrics.histogram_stats("scorer.deepseek.empty_content.completion_tokens")["max"] == 16_384
    assert metrics.histogram_stats("scorer.deepseek.empty_content.reasoning_tokens")["max"] == 16_384
    assert completed["component"] == "triage"
    assert completed["max_tokens"] == 16_384
    assert completed["success"] is False
    assert completed["metadata"]["finish_reason"] == "length"
    assert "finish_reason=length" in completed["error_message"]


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


def test_call_deepseek_uses_strict_beta_tool_for_json_schema(monkeypatch) -> None:
    seen: dict = {}

    class StrictResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {"function": {"name": "emit_result", "arguments": '{"result":[{"id":"1"}]}'}},
                            ],
                        },
                    },
                ],
                "usage": {},
            }

    def fake_post(url, *, headers, json, timeout):
        seen.update(url=url, payload=json)
        return StrictResponse()

    monkeypatch.setattr(llm_client, "get_deepseek_api_key", lambda: "test-key")
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(llm_client, "record_llm_usage", lambda **kwargs: None)
    schema = {"type": "array", "items": {"type": "object"}}

    result = llm_client._call_deepseek("deepseek-v4-flash", "prompt", json_schema=schema)

    assert result == '[{"id": "1"}]'
    assert seen["url"] == "https://api.deepseek.com/beta/chat/completions"
    assert seen["payload"]["model"] == "deepseek-v4-flash"
    assert seen["payload"]["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in seen["payload"]
    assert seen["payload"]["tools"][0]["function"]["strict"] is True
    assert seen["payload"]["tools"][0]["function"]["parameters"]["properties"]["result"] == schema
    assert seen["payload"]["tool_choice"] == {"type": "function", "function": {"name": "emit_result"}}


def test_call_gemini_uses_standard_response_json_schema(monkeypatch) -> None:
    captured = {}

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            captured.update(model=model, contents=contents, config=config)
            return type("Response", (), {"text": "[]", "usage_metadata": None})()

    fake_client = type("Client", (), {"models": FakeModels()})()
    monkeypatch.setattr(llm_client, "get_gemini_client", lambda: fake_client)
    monkeypatch.setattr(llm_client, "record_llm_usage", lambda **kwargs: None)
    schema = {"type": "array", "items": {"type": "string"}}

    assert llm_client._call_gemini("gemini-test", "prompt", json_schema=schema) == "[]"
    assert captured["config"].response_mime_type == "application/json"
    assert captured["config"].response_json_schema == schema


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
