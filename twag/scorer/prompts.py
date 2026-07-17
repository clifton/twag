"""Prompt templates for LLM scoring and analysis."""

# Triage prompt for fast scoring
TRIAGE_PROMPT = """You are a financial markets triage agent. Score this tweet 0-10 for relevance to macro/investing.

Categories (assign 1-3 that apply): fed_policy, inflation, job_market, macro_data, earnings, equities, rates_fx, credit, banks, consumer_spending, capex, commodities, energy, metals_mining, geopolitical, sanctions, tech_business, ai_advancement, crypto, noise

Tweet: {tweet_text}
Author: @{handle}

Return JSON only:
{{"score": 7, "categories": ["fed_policy", "rates_fx"], "summary": "One-liner summary", "tickers": ["TLT", "GLD"]}}"""

# Batch triage prompt. Render this with literal str.replace calls, never str.format.
BATCH_TRIAGE_PROMPT = """You are the triage desk for a discretionary global-macro fund. Score each tweet 0-10 for usefulness to the fund TODAY. The fund's edge is taking duration on SURPRISES — moments the tape or data did something the consensus narrative did not predict. Narrative is what everyone already knows; it scores low. A surprise that lands on a live theme or matches a playbook trigger scores high.

FUND CONTEXT (what the fund cares about right now):
{fund_context}

SCORE ANCHORS:
- 9-10: Confirmed playbook trigger, or a major surprise directly hitting a live theme or owned instrument (confirmed physical supply loss, hawkish repricing on hard data, capability release naming victims, forced-seller stress). Act-now information.
- 7-8: New primary datapoint that materially advances or damages a live theme; a credible surprise on a watch theme; a dated catalyst added, moved, or RESOLVED for anything in fund context.
- 5-6: Useful new datapoint or well-sourced flow/positioning color; secondary confirmation of something already known; relevant but not theme-moving.
- 3-4: Market-relevant narrative, opinion, or commentary with no new data; repeats of already-circulating news; generic macro takes.
- 0-2: Noise, engagement bait, off-topic, memes, stale threads.

HARD RULES:
- Narrative cap: opinion or thesis restating what is already priced and known scores AT MOST 4, regardless of author.
- Stale-repeat cap: if this repeats news already circulating (same print reworded, aggregator recycling a headline), set is_stale_repeat true and score at most 4 — UNLESS it adds a genuinely new datapoint (a new number, a primary source, official confirmation of a rumor), which is not stale.
- Primary beats aggregator: an original source (author's own data, filing, official statement, journalist breaking) outranks an aggregator repost of the same fact. Score the aggregator copy lower.
- Resolution matters as much as escalation: a ceasefire, settlement, framework, guidance withdrawal, or de-escalation that RESOLVES a known catalyst or kills a crisis premium is high-value (7+). The fund must exit catalyst trades when the catalyst dies. Set catalyst to "resolved".
- Author prior is a prior, not a verdict: tier-1 or high-average authors get benefit of the doubt on terse posts; unknown accounts making big claims without a source score lower.

SURPRISE (integer):
- 2 = the tape or data did something the prevailing narrative did not predict (unexpected print, price reaction inconsistent with consensus, out-of-the-blue event).
- 1 = new datapoint, roughly in line with expectations but additive.
- 0 = narrative, opinion, or repetition; no new information about the world.

PLAYBOOK TRIGGERS — set playbook_trigger to the FIRST that clearly matches, else "none". Match conservatively; a trigger requires the tweet's own facts, not your extrapolation:
- "supply_shock": confirmed physical supply loss >1-2% of global supply of a traded commodity (outage, force majeure, export ban, blockade) within roughly the last 48h.
- "supercycle": commodity or physical-good spot price up ~20%+ over ~3 months WITH producer margin expansion or capacity-discipline evidence.
- "vol_substitution": the tweet itself states that the direct expression of a shock has rich vol (IV spiking or >80th percentile) while a correlated FX/rates expression is still cheap (<50th percentile). Expect this to be rare — match only when the tweet carries the configuration.
- "ai_victim": major AI capability release, or sector evidence within ~5 days of one, naming or implying cash-flow victims (IT services, BPO, staffing, legacy software).
- "event_reset": earnings gap >+15% in a beaten-down, high-short-interest name near the bottom of its range — a forced repricing.
- "dat_mnav": digital-asset treasury company at mNAV <1.2x, or preferred obligations vs reserves stress, or an announced framework/monetization that RESOLVES such stress.
- "defensive_break": expensive defensive (staples/healthcare/utility at premium multiple) showing fundamental deterioration into a dated catalyst window.

THEMES: assign 0-3. Prefer exact ids from LIVE THEMES in fund context. If a tweet clearly belongs to an emerging story no live theme covers, propose "new:<short-slug>" (e.g. "new:japan-fiscal-snap"). Do not force a theme onto generic macro chatter.

CATEGORIES (coarse filter, assign 1-3): {categories}

Tweets (each line is "[id] @handle (author context): text"):
{tweets}

Return a JSON array with one object per tweet, in order:
[{"id": "tweet_id", "score": 7, "surprise": 1, "is_stale_repeat": false, "categories": ["commodities"], "themes": ["ai-memory"], "playbook_trigger": "none", "catalyst": "none", "direction": "long", "tickers": ["MU"], "summary": "The compressed fact: numbers, dates, tickers."}]

- "catalyst": "scheduled" if the tweet adds or moves a dated future event relevant to fund context; "resolved" if it resolves or kills a known catalyst or crisis premium; else "none".
- "direction": "long" or "short" when the tweet's own facts clearly imply a directional read for the named tickers or theme; "na" when unclear or two-sided.
- "summary" is the fact itself, telegraphic, never commentary about the tweet.
"""

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
