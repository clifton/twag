"""Configuration management for twag."""

import json
import os
from pathlib import Path
from typing import Any

# Application name for XDG paths
APP_NAME = "twag"

# Default configuration
DEFAULT_CONFIG: dict[str, Any] = {
    "llm": {
        "triage_model": "gemini-3-flash-preview",
        "triage_provider": "gemini",
        "enrichment_model": "claude-opus-4-5-20251101",
        "enrichment_provider": "anthropic",
        "vision_model": "gemini-3-flash-preview",
        "vision_provider": "gemini",
        "max_concurrency_triage": 6,
        "max_concurrency_text": 12,
        "max_concurrency_vision": 6,
        "retry_max_attempts": 4,
        "retry_base_seconds": 1.0,
        "retry_max_seconds": 20.0,
        "retry_jitter": 0.3,
    },
    "scoring": {
        "min_score_for_digest": 5,
        "high_signal_threshold": 7,
        "alert_threshold": 8,
        "batch_size": 15,
        "min_score_for_reprocess": 3,
        "min_score_for_media": 3,
        "min_score_for_analysis": 3,
        "min_score_for_article_processing": 5,
    },
    "notifications": {
        "telegram_enabled": True,
        "telegram_chat_id": None,
        "quiet_hours_start": 23,
        "quiet_hours_end": 8,
        "max_alerts_per_hour": 10,
    },
    "accounts": {
        "decay_rate": 0.05,
        "boost_increment": 5,
        "auto_promote_threshold": 75,
    },
    "fetch": {
        "tier1_delay": 3,  # seconds between tier-1 account fetches
        "tier1_stagger": 5,  # number of tier-1 accounts per fetch run (None = all)
        "quote_depth": 3,  # max recursive depth for quoted tweets
        "quote_delay": 1.0,  # seconds between recursive quoted tweet fetches
    },
    "processing": {
        "max_concurrency_url_expansion": 15,
    },
    "paths": {
        # These can be overridden in config.json
        # If not set, XDG defaults are used
        "data_dir": None,  # Override for all data (db, following, digests)
    },
    "bird": {
        "auth_token_env": "AUTH_TOKEN",
        "ct0_env": "CT0",
        "min_interval_seconds": 1.0,
        "retry_max_attempts": 4,
        "retry_base_seconds": 15.0,
        "retry_max_seconds": 120.0,
    },
}


def get_xdg_config_home() -> Path:
    """Get XDG config home directory."""
    return Path(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")))


def get_xdg_data_home() -> Path:
    """Get XDG data home directory."""
    return Path(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")))


def get_config_path() -> Path:
    """Get the path to the config file."""
    return get_xdg_config_home() / APP_NAME / "config.json"


def load_config() -> dict[str, Any]:
    """Load configuration, merging with defaults."""
    config = DEFAULT_CONFIG.copy()
    config_path = get_config_path()

    if config_path.exists():
        with open(config_path) as f:
            user_config = json.load(f)
            config = deep_merge(config, user_config)

    return config


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to file."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_data_dir() -> Path:
    """
    Get the data directory for twag.

    Priority:
    1. TWAG_DATA_DIR environment variable
    2. paths.data_dir in config.json
    3. XDG default: ~/.local/share/twag/
    """
    # 1. Environment variable takes highest priority
    env_dir = os.environ.get("TWAG_DATA_DIR")
    if env_dir:
        return Path(env_dir)

    # 2. Config file override
    config = load_config()
    config_dir = config.get("paths", {}).get("data_dir")
    if config_dir:
        return Path(config_dir)

    # 3. XDG default
    return get_xdg_data_home() / APP_NAME


def get_database_path() -> Path:
    """Get the database path."""
    return get_data_dir() / "twag.db"


def get_digests_dir() -> Path:
    """Get the digests directory path."""
    return get_data_dir() / "digests"


def get_following_path() -> Path:
    """Get the following list path."""
    return get_data_dir() / "following.txt"


# Backward compatibility aliases
def get_memory_dir() -> Path:
    """
    Get the data directory (legacy alias).

    DEPRECATED: Use get_data_dir() or get_digests_dir() instead.
    """
    return get_data_dir()


def get_workspace_path() -> Path:
    """
    Get the data directory (legacy alias).

    DEPRECATED: Use get_data_dir() instead.
    """
    return get_data_dir()
