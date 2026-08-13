"""Tests for default configuration."""

from twag.config import DEFAULT_CONFIG


def test_default_triage_uses_deepseek_v4_flash() -> None:
    llm_config = DEFAULT_CONFIG["llm"]

    assert llm_config["triage_model"] == "deepseek-v4-flash"
    assert llm_config["triage_provider"] == "deepseek"
    assert llm_config["triage_reasoning"] == "high"
    assert llm_config["triage_max_tokens"] == 16_384


def test_default_vision_uses_gemini_36_flash() -> None:
    assert DEFAULT_CONFIG["llm"]["vision_model"] == "gemini-3.6-flash"
