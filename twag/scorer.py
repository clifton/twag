"""LLM-powered tweet scoring and analysis."""

import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any

from anthropic import Anthropic

from .config import load_config

# Triage prompt for fast scoring
TRIAGE_PROMPT = """You are a financial markets triage agent. Score this tweet 0-10 for relevance to macro/investing.

Categories (assign 1-3 that apply): fed_policy, inflation, job_market, macro_data, earnings, equities, rates_fx, credit, banks, consumer_spending, capex, commodities, energy, metals_mining, geopolitical, sanctions, tech_business, ai_advancement, crypto, noise

Tweet: {tweet_text}
Author: @{handle}

Return JSON only:
{{"score": 7, "categories": ["fed_policy", "rates_fx"], "summary": "One-liner summary", "tickers": ["TLT", "GLD"]}}"""

# Batch triage prompt
BATCH_TRIAGE_PROMPT = """You are a financial markets triage agent. Score these tweets 0-10 for relevance to macro/investing.

Categories (assign 1-3 that apply): fed_policy, inflation, job_market, macro_data, earnings, equities, rates_fx, credit, banks, consumer_spending, capex, commodities, energy, metals_mining, geopolitical, sanctions, tech_business, ai_advancement, crypto, noise

Tweets:
{tweets}

Return a JSON array with one object per tweet, in order:
[{{"id": "tweet_id", "score": 7, "categories": ["fed_policy", "rates_fx"], "summary": "One-liner", "tickers": ["TLT"]}}]"""

# Enrichment prompt for high-signal tweets
ENRICHMENT_PROMPT = """You are a financial analyst. Analyze this tweet for actionable insights.

Tweet: {tweet_text}
Author: @{handle} ({author_category})
Quoted: {quoted_tweet}
Linked article: {article_summary}
Media context: {image_description}

Provide:
1. Signal tier: high_signal | market_relevant | news | noise
2. Key insight (1-2 sentences)
3. Investment implications with specific tickers
4. Any emerging narratives this connects to

Return JSON:
{{"signal_tier": "high_signal", "insight": "...", "implications": "...", "narratives": ["Fed pivot"], "tickers": ["TLT"]}}"""

# Content summarization prompt for long tweets
SUMMARIZE_PROMPT = """Summarize this tweet concisely while preserving all key market-relevant information, data points, and actionable insights. Keep ticker symbols and specific numbers.

Tweet by @{handle}:
{tweet_text}

Provide a summary in 2-4 sentences (under 400 characters). Return only the summary text, no JSON."""

# Document text summarization prompt for OCR output
DOCUMENT_SUMMARY_PROMPT = """Summarize the following document text in 2 concise lines.
Do not start with "This text" or similar phrasing.
Highlight the most important facts, numbers, or claims.
Return only the two lines, no JSON.

Document text:
{document_text}
"""

# Vision prompt for chart analysis
MEDIA_PROMPT = """Analyze this image from a financial Twitter post.

Determine if it is a chart, a table/spreadsheet, a document/screen with coherent prose, or a meme/photo/other.

Return JSON:
{
  "kind": "chart|table|document|screenshot|meme|photo|other",
  "short_description": "very short description (3-8 words)",
  "prose_text": "FULL text if it's coherent prose; otherwise empty string",
  "prose_summary": "two concise lines summarizing the prose; otherwise empty string",
  "chart": {
    "type": "line|bar|candlestick|heatmap|other",
    "description": "what data is shown",
    "insight": "key visual insight",
    "implication": "investment implication",
    "tickers": ["AAPL"]
  },
  "table": {
    "title": "optional table title",
    "description": "what data the table shows",
    "columns": ["Col1", "Col2", "Col3"],
    "rows": [["val1", "val2", "val3"], ["val4", "val5", "val6"]],
    "summary": "2-line summary of key insights from the data",
    "tickers": ["AAPL"]
  }
}

Rules:
- If the image is a table (spreadsheet, data grid, financial table), set kind to "table".
- Extract ALL visible rows and columns into table.columns and table.rows.
- table.summary should highlight the most important data points.
- Keep kind "chart" for line/bar/candlestick visualizations only.
- If NOT a chart, set chart fields to empty strings and [].
- If NOT a table, set table fields to empty strings, [] and {}.
- If there is not coherent prose, set prose_text to "".
- If prose_text is provided, preserve paragraphs and wording as written.
- prose_summary should be 2 short lines, highlight important bits, no preamble like \"This text\".
- short_description should be very short and neutral.
"""


@dataclass
class TriageResult:
    """Result of tweet triage scoring."""

    tweet_id: str
    score: float
    categories: list[str]
    summary: str
    tickers: list[str] = field(default_factory=list)


@dataclass
class EnrichmentResult:
    """Result of tweet enrichment analysis."""

    signal_tier: str
    insight: str
    implications: str
    narratives: list[str] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)


@dataclass
class VisionResult:
    """Result of chart/image analysis."""

    chart_type: str
    description: str
    insight: str
    implication: str
    tickers: list[str] = field(default_factory=list)


@dataclass
class MediaAnalysisResult:
    """Result of image/media analysis."""

    kind: str
    short_description: str
    prose_text: str
    prose_summary: str
    chart: dict[str, Any] = field(default_factory=dict)
    table: dict[str, Any] = field(default_factory=dict)


def _load_env_file() -> dict[str, str]:
    """Load environment variables from ~/.env."""
    env_file = os.path.expanduser("~/.env")
    env = {}

    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    if line.startswith("export "):
                        line = line[7:]
                    key, value = line.split("=", 1)
                    value = value.strip("\"'")
                    env[key] = value

    return env


def _get_api_key(key_name: str) -> str:
    """Get an API key from environment or ~/.env."""
    api_key = os.environ.get(key_name)

    if not api_key:
        env = _load_env_file()
        api_key = env.get(key_name)

    if not api_key:
        raise RuntimeError(f"{key_name} not set")

    return api_key


def get_anthropic_client() -> Anthropic:
    """Get an Anthropic client."""
    return Anthropic(api_key=_get_api_key("ANTHROPIC_API_KEY"))


def get_gemini_client():
    """Get a Gemini client using the new google.genai SDK."""
    from google import genai

    return genai.Client(api_key=_get_api_key("GEMINI_API_KEY"))


def _call_anthropic(model: str, prompt: str, max_tokens: int = 2048) -> str:
    """Call Anthropic API and return text response."""
    client = get_anthropic_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _call_gemini(model: str, prompt: str, max_tokens: int = 2048, reasoning: str | None = None) -> str:
    """Call Gemini API and return text response."""
    from google.genai import types

    client = get_gemini_client()

    config_kwargs: dict = {"max_output_tokens": max_tokens}

    # Add thinking config if reasoning is specified
    if reasoning:
        # Gemini 3+ uses thinking_level (string: "low", "medium", "high")
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=reasoning)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    return response.text


def _call_anthropic_vision(model: str, image_url: str, prompt: str, max_tokens: int = 1024) -> str:
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
    return response.content[0].text


def _call_gemini_vision(model: str, image_url: str, prompt: str, max_tokens: int = 1024) -> str:
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
    return response.text


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


def triage_tweet(
    tweet_id: str,
    tweet_text: str,
    handle: str,
    model: str | None = None,
    provider: str | None = None,
) -> TriageResult:
    """Score a single tweet for relevance."""
    config = load_config()
    model = model or config["llm"]["triage_model"]
    provider = provider or config["llm"].get("triage_provider", "anthropic")

    prompt = TRIAGE_PROMPT.format(tweet_text=tweet_text, handle=handle)
    text = _call_llm(provider, model, prompt, max_tokens=512)
    data = _parse_json_response(text)

    if isinstance(data, list):
        data = data[0]

    # Handle both old "category" (string) and new "categories" (array) format
    categories = data.get("categories") or [data.get("category", "noise")]
    if isinstance(categories, str):
        categories = [categories]

    return TriageResult(
        tweet_id=tweet_id,
        score=float(data.get("score", 0)),
        categories=categories,
        summary=data.get("summary", ""),
        tickers=data.get("tickers", []),
    )


def triage_tweets_batch(
    tweets: list[dict[str, str]],
    model: str | None = None,
    provider: str | None = None,
) -> list[TriageResult]:
    """Score multiple tweets in a single API call.

    Args:
        tweets: List of dicts with 'id', 'text', 'handle' keys
        model: Model to use (defaults to config triage_model)
        provider: Provider to use (defaults to config triage_provider)
    """
    if not tweets:
        return []

    config = load_config()
    model = model or config["llm"]["triage_model"]
    provider = provider or config["llm"].get("triage_provider", "anthropic")

    # Format tweets for prompt
    tweets_text = "\n\n".join(f"[{t['id']}] @{t['handle']}: {t['text']}" for t in tweets)

    prompt = BATCH_TRIAGE_PROMPT.format(tweets=tweets_text)
    text = _call_llm(provider, model, prompt, max_tokens=16384)
    data = _parse_json_response(text)

    if not isinstance(data, list):
        data = [data]

    results = []
    for item in data:
        # Handle both old "category" (string) and new "categories" (array) format
        categories = item.get("categories") or [item.get("category", "noise")]
        if isinstance(categories, str):
            categories = [categories]

        results.append(
            TriageResult(
                tweet_id=str(item.get("id", "")),
                score=float(item.get("score", 0)),
                categories=categories,
                summary=item.get("summary", ""),
                tickers=item.get("tickers", []),
            )
        )

    return results


def enrich_tweet(
    tweet_text: str,
    handle: str,
    author_category: str = "unknown",
    quoted_tweet: str = "",
    article_summary: str = "",
    image_description: str = "",
    model: str | None = None,
    provider: str | None = None,
) -> EnrichmentResult:
    """Deep analysis of a high-signal tweet."""
    config = load_config()
    model = model or config["llm"]["enrichment_model"]
    provider = provider or config["llm"].get("enrichment_provider", "anthropic")
    reasoning = config["llm"].get("enrichment_reasoning")

    prompt = ENRICHMENT_PROMPT.format(
        tweet_text=tweet_text,
        handle=handle,
        author_category=author_category,
        quoted_tweet=quoted_tweet or "[none]",
        article_summary=article_summary or "[none]",
        image_description=image_description or "[none]",
    )

    text = _call_llm(provider, model, prompt, max_tokens=2048, reasoning=reasoning)
    data = _parse_json_response(text)

    if isinstance(data, list):
        data = data[0]

    return EnrichmentResult(
        signal_tier=data.get("signal_tier", "noise"),
        insight=data.get("insight", ""),
        implications=data.get("implications", ""),
        narratives=data.get("narratives", []),
        tickers=data.get("tickers", []),
    )


def summarize_tweet(
    tweet_text: str,
    handle: str,
    model: str | None = None,
    provider: str | None = None,
) -> str:
    """Summarize a long tweet. Uses enrichment model by default."""
    config = load_config()
    model = model or config["llm"]["enrichment_model"]
    provider = provider or config["llm"].get("enrichment_provider", "anthropic")
    reasoning = config["llm"].get("enrichment_reasoning")

    prompt = SUMMARIZE_PROMPT.format(tweet_text=tweet_text, handle=handle)
    text = _call_llm(provider, model, prompt, max_tokens=1024, reasoning=reasoning)

    # Return raw text (not JSON)
    return text.strip()


def summarize_document_text(
    document_text: str,
    model: str | None = None,
    provider: str | None = None,
) -> str:
    """Summarize OCR document text into two concise lines."""
    config = load_config()
    model = model or config["llm"]["enrichment_model"]
    provider = provider or config["llm"].get("enrichment_provider", "anthropic")
    reasoning = config["llm"].get("enrichment_reasoning")

    prompt = DOCUMENT_SUMMARY_PROMPT.format(document_text=document_text)
    text = _call_llm(provider, model, prompt, max_tokens=256, reasoning=reasoning)
    return text.strip()


def analyze_image(
    image_url: str,
    model: str | None = None,
    provider: str | None = None,
) -> MediaAnalysisResult:
    """Analyze a chart or image from a tweet."""
    config = load_config()
    model = model or config["llm"]["vision_model"]
    provider = provider or config["llm"].get("vision_provider", "anthropic")

    text = _call_llm_vision(provider, model, image_url, MEDIA_PROMPT, max_tokens=4096)
    data = _parse_json_response(text)

    if isinstance(data, list):
        data = data[0]

    chart = data.get("chart") or {}
    if not isinstance(chart, dict):
        chart = {}

    table = data.get("table") or {}
    if not isinstance(table, dict):
        table = {}

    return MediaAnalysisResult(
        kind=(data.get("kind", "other") or "other").lower(),
        short_description=(data.get("short_description") or "").strip(),
        prose_text=(data.get("prose_text") or "").strip(),
        prose_summary=(data.get("prose_summary") or "").strip(),
        chart={
            "type": chart.get("type", ""),
            "description": chart.get("description", ""),
            "insight": chart.get("insight", ""),
            "implication": chart.get("implication", ""),
            "tickers": chart.get("tickers", []),
        },
        table={
            "title": table.get("title", ""),
            "description": table.get("description", ""),
            "columns": table.get("columns", []),
            "rows": table.get("rows", []),
            "summary": table.get("summary", ""),
            "tickers": table.get("tickers", []),
        },
    )


def analyze_media(
    image_url: str,
    model: str | None = None,
    provider: str | None = None,
) -> MediaAnalysisResult:
    """Analyze any tweet media image with OCR and classification."""
    return analyze_image(image_url=image_url, model=model, provider=provider)
