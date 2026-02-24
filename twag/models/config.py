"""Pydantic models for twag configuration."""

from __future__ import annotations

from pydantic import BaseModel


class LLMConfig(BaseModel):
    """LLM provider and model configuration."""

    triage_model: str = "gemini-3-flash-preview"
    triage_provider: str = "gemini"
    enrichment_model: str = "gemini-3.1-pro-preview"
    enrichment_provider: str = "gemini"
    enrichment_reasoning: str | None = None
    vision_model: str = "gemini-3-flash-preview"
    vision_provider: str = "gemini"
    max_concurrency_triage: int = 4
    max_concurrency_text: int = 8
    max_concurrency_vision: int = 4
    retry_max_attempts: int = 4
    retry_base_seconds: float = 1.0
    retry_max_seconds: float = 20.0
    retry_jitter: float = 0.3


class ScoringConfig(BaseModel):
    """Scoring thresholds configuration."""

    min_score_for_digest: int = 5
    high_signal_threshold: int = 7
    alert_threshold: int = 8
    batch_size: int = 15
    min_score_for_reprocess: int = 3
    min_score_for_media: int = 3
    min_score_for_analysis: int = 3
    min_score_for_article_processing: int = 5


class NotificationConfig(BaseModel):
    """Notification configuration."""

    telegram_enabled: bool = True
    telegram_chat_id: str | None = None
    quiet_hours_start: int = 23
    quiet_hours_end: int = 8
    max_alerts_per_hour: int = 10


class AccountsConfig(BaseModel):
    """Account management configuration."""

    decay_rate: float = 0.05
    boost_increment: int = 5
    auto_promote_threshold: int = 75


class FetchConfig(BaseModel):
    """Fetch configuration."""

    tier1_delay: int = 3
    tier1_stagger: int = 5
    quote_depth: int = 3
    quote_delay: float = 1.0


class ProcessingConfig(BaseModel):
    """Processing configuration."""

    max_concurrency_url_expansion: int = 15


class PathsConfig(BaseModel):
    """Paths configuration."""

    data_dir: str | None = None


class BirdConfig(BaseModel):
    """Bird CLI configuration."""

    auth_token_env: str = "AUTH_TOKEN"
    ct0_env: str = "CT0"
    min_interval_seconds: float = 1.0


class TwagConfig(BaseModel):
    """Top-level twag configuration."""

    llm: LLMConfig = LLMConfig()
    scoring: ScoringConfig = ScoringConfig()
    notifications: NotificationConfig = NotificationConfig()
    accounts: AccountsConfig = AccountsConfig()
    fetch: FetchConfig = FetchConfig()
    processing: ProcessingConfig = ProcessingConfig()
    paths: PathsConfig = PathsConfig()
    bird: BirdConfig = BirdConfig()
