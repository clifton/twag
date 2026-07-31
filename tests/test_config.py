"""Tests for default configuration."""

from twag.config import load_config


def test_default_triage_uses_deepseek_v4_flash() -> None:
    llm_config = load_config()["llm"]

    assert llm_config["triage_model"] == "deepseek-v4-flash"
    assert llm_config["triage_provider"] == "deepseek"
    assert llm_config["triage_reasoning"] == "high"
