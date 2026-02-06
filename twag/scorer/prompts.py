"""Prompt templates for LLM scoring and analysis."""

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

# X article summarization prompt for long-form status articles
ARTICLE_SUMMARY_PROMPT = """You are a buy-side markets analyst. Analyze this X article and return structured output.

Title: {article_title}
Preview: {article_preview}
Article text:
{article_text}

Return JSON only:
{{
  "short_summary": "2-4 concise lines max",
  "primary_points": [
    {{
      "point": "Main claim or takeaway",
      "reasoning": "Why this point is argued",
      "evidence": "Specific figures, comparisons, or facts from article"
    }}
  ],
  "actionable_items": [
    {{
      "action": "Monitor/position/hedge idea",
      "trigger": "What confirms or invalidates",
      "horizon": "near_term|medium_term|long_term",
      "confidence": 0.0,
      "tickers": ["GOOGL"]
    }}
  ]
}}

Rules:
- Include at most 6 primary_points.
- Include actionable_items only when evidence supports action; otherwise return [].
- Confidence must be between 0 and 1.
- Keep every statement grounded in the article text.
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
