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


def test_call_deepseek_uses_thinking_high_by_default(monkeypatch) -> None:
    seen: dict = {}
    logged: dict = {}

    def _fake_post(url, *, headers, json, timeout):
        seen["url"] = url
        seen["headers"] = headers
        seen["json"] = json
        seen["timeout"] = timeout
        return _FakeDeepSeekResponse()

    monkeypatch.setattr(llm_client, "get_deepseek_api_key", lambda: "test-key")
    monkeypatch.setattr(httpx, "post", _fake_post)
    monkeypatch.setattr(llm_client, "record_llm_usage", lambda **kwargs: logged.update(kwargs))

    result = llm_client._call_deepseek("deepseek-v4-pro", "hello", max_tokens=12)

    assert result == "ok"
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert seen["json"]["model"] == "deepseek-v4-pro"
    assert seen["json"]["messages"] == [{"role": "user", "content": "hello"}]
    assert seen["json"]["thinking"] == {"type": "enabled"}
    assert seen["json"]["reasoning_effort"] == "high"
    assert seen["json"]["max_tokens"] == 12
    assert seen["timeout"] == 120
    assert logged["component"] == "unknown"
    assert logged["provider"] == "deepseek"
    assert logged["input_tokens"] == 11
    assert logged["output_tokens"] == 7
    assert logged["success"] is True


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
    assert seen["payload"]["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in seen["payload"]
    assert seen["payload"]["tools"][0]["function"]["strict"] is True
    assert seen["payload"]["tools"][0]["function"]["parameters"]["properties"]["result"] == schema


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
        ("low", "high"),
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
