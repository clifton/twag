#!/usr/bin/env python3
"""Test that all configured LLM models are working."""

import sys

import pytest

from twag.config import load_config
from twag.scorer import (
    _call_llm,
    _get_api_key,
    get_anthropic_client,
    get_gemini_client,
)


def test_api_keys():
    """Check that required API keys are available."""
    print("Testing API keys...")

    keys = ["ANTHROPIC_API_KEY", "GEMINI_API_KEY"]
    all_ok = True

    for key in keys:
        try:
            val = _get_api_key(key)
            masked = val[:8] + "..." + val[-4:] if len(val) > 12 else "***"
            print(f"  ✓ {key}: {masked}")
        except RuntimeError as e:
            print(f"  ✗ {key}: MISSING")
            all_ok = False

    assert all_ok, "Missing one or more required API keys."


def test_anthropic_client():
    """Test Anthropic API connection."""
    print("\nTesting Anthropic client...")

    try:
        client = get_anthropic_client()
        print(f"  ✓ Client created")
    except Exception as e:
        pytest.fail(f"Anthropic client failed: {e}")


def test_gemini_client():
    """Test Gemini API connection."""
    print("\nTesting Gemini client...")

    try:
        client = get_gemini_client()
        print(f"  ✓ Client created")
    except Exception as e:
        pytest.fail(f"Gemini client failed: {e}")


def test_triage_model():
    """Test the triage model (Gemini)."""
    config = load_config()
    model = config["llm"]["triage_model"]
    provider = config["llm"].get("triage_provider", "anthropic")

    print(f"\nTesting triage model: {model} ({provider})...")

    test_prompt = """Score this tweet 0-10 for financial markets relevance.
Tweet: "Fed raises rates by 25bp, signals more hikes ahead"
Return JSON: {"score": 7, "reason": "test"}"""

    try:
        response = _call_llm(provider, model, test_prompt, max_tokens=100)
        print(f"  ✓ Response received ({len(response)} chars)")
        print(f"    Preview: {response[:100]}...")
    except Exception as e:
        pytest.fail(f"Triage model failed: {e}")


def test_enrichment_model():
    """Test the enrichment model (Anthropic)."""
    config = load_config()
    model = config["llm"]["enrichment_model"]
    provider = config["llm"].get("enrichment_provider", "anthropic")

    print(f"\nTesting enrichment model: {model} ({provider})...")

    test_prompt = """Summarize this in one sentence: The Federal Reserve announced a 25 basis point rate hike today."""

    try:
        response = _call_llm(provider, model, test_prompt, max_tokens=100)
        print(f"  ✓ Response received ({len(response)} chars)")
        print(f"    Preview: {response[:100]}...")
    except Exception as e:
        pytest.fail(f"Enrichment model failed: {e}")


def test_vision_model():
    """Test the vision model (Gemini)."""
    config = load_config()
    model = config["llm"]["vision_model"]
    provider = config["llm"].get("vision_provider", "anthropic")

    print(f"\nTesting vision model: {model} ({provider})...")
    pytest.skip("Skipping (requires image URL)")


def main():
    print("=" * 50)
    print("TWAG Model Configuration Test")
    print("=" * 50)

    config = load_config()
    print("\nConfigured models:")
    print(f"  Triage:     {config['llm']['triage_model']} ({config['llm'].get('triage_provider', 'anthropic')})")
    print(f"  Enrichment: {config['llm']['enrichment_model']} ({config['llm'].get('enrichment_provider', 'anthropic')})")
    print(f"  Vision:     {config['llm']['vision_model']} ({config['llm'].get('vision_provider', 'anthropic')})")

    results = []

    results.append(("API Keys", test_api_keys()))
    results.append(("Anthropic Client", test_anthropic_client()))
    results.append(("Gemini Client", test_gemini_client()))
    results.append(("Triage Model", test_triage_model()))
    results.append(("Enrichment Model", test_enrichment_model()))
    results.append(("Vision Model", test_vision_model()))

    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
