"""Centralized metric name taxonomy.

All metric names are defined here as constants to ensure consistent naming
across the codebase. Convention: {subsystem}_{provider?}_{object}_{qualifier}_{unit?}
with singular nouns throughout.

Subsystems: bird, llm, pipeline, telegram, http, link
"""

# -- bird (CLI fetch layer) --------------------------------------------------
BIRD_CALL_DURATION_SECONDS = "bird_call_duration_seconds"
BIRD_CALL_SUCCESS = "bird_call_success"
BIRD_CALL_FAILURE = "bird_call_failure"
BIRD_TWEET_FETCHED = "bird_tweet_fetched"

# -- llm (scoring / enrichment) ----------------------------------------------
# Anthropic
LLM_ANTHROPIC_CALL = "llm_anthropic_call"
LLM_ANTHROPIC_CALL_DURATION_SECONDS = "llm_anthropic_call_duration_seconds"
LLM_ANTHROPIC_TOKEN_INPUT = "llm_anthropic_token_input"
LLM_ANTHROPIC_TOKEN_OUTPUT = "llm_anthropic_token_output"

# Gemini
LLM_GEMINI_CALL = "llm_gemini_call"
LLM_GEMINI_CALL_DURATION_SECONDS = "llm_gemini_call_duration_seconds"
LLM_GEMINI_TOKEN_INPUT = "llm_gemini_token_input"
LLM_GEMINI_TOKEN_OUTPUT = "llm_gemini_token_output"

# Provider-agnostic
LLM_RETRY = "llm_retry"
LLM_ERROR = "llm_error"

# -- link (URL expansion) ----------------------------------------------------
LINK_EXPANSION_DURATION_SECONDS = "link_expansion_duration_seconds"
LINK_EXPANSION_FAILURE = "link_expansion_failure"

# -- pipeline (processing orchestration) -------------------------------------
PIPELINE_PROCESS_DURATION_SECONDS = "pipeline_process_duration_seconds"
PIPELINE_TWEET_TOTAL = "pipeline_tweet_total"
PIPELINE_CYCLE_DURATION_SECONDS = "pipeline_cycle_duration_seconds"

# -- telegram (notifications) ------------------------------------------------
TELEGRAM_SEND_SUCCESS = "telegram_send_success"
TELEGRAM_SEND_FAILURE = "telegram_send_failure"

# -- http (web layer) --------------------------------------------------------
HTTP_REQUEST_DURATION_SECONDS = "http_request_duration_seconds"


def http_request_counter_name(method: str, status: int) -> str:
    """Build a dynamic HTTP request counter name: http_request_{METHOD}_{STATUS}."""
    return f"http_request_{method}_{status}"
