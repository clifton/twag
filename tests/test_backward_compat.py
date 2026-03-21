"""Backward-compatibility contract tests.

These tests pin the public surface area of twag so that accidental removals
or renames of public symbols, CLI commands, DB columns, or API endpoints
are caught before they ship.
"""

from __future__ import annotations

import sqlite3
from typing import ClassVar

import pytest

# ---------------------------------------------------------------------------
# (a) CLI command registry
# ---------------------------------------------------------------------------


class TestCLICommands:
    """Assert every expected Click command/subcommand exists."""

    @pytest.fixture()
    def cli_group(self):
        from twag.cli import cli

        return cli

    TOP_LEVEL: ClassVar[set[str]] = {
        "init",
        "doctor",
        "fetch",
        "process",
        "analyze",
        "digest",
        "accounts",
        "narratives",
        "stats",
        "prune",
        "export",
        "config",
        "db",
        "search",
        "web",
    }

    ACCOUNTS_SUBS: ClassVar[set[str]] = {"list", "add", "promote", "mute", "demote", "decay", "boost", "import"}
    NARRATIVES_SUBS: ClassVar[set[str]] = {"list"}
    CONFIG_SUBS: ClassVar[set[str]] = {"show", "path", "set"}
    DB_SUBS: ClassVar[set[str]] = {"path", "shell", "init", "rebuild-fts", "dump", "restore"}

    def test_top_level_commands(self, cli_group):
        registered = set(cli_group.commands)
        missing = self.TOP_LEVEL - registered
        assert not missing, f"Missing top-level CLI commands: {missing}"

    @pytest.mark.parametrize(
        "group_name,expected",
        [
            ("accounts", ACCOUNTS_SUBS),
            ("narratives", NARRATIVES_SUBS),
            ("config", CONFIG_SUBS),
            ("db", DB_SUBS),
        ],
    )
    def test_subcommands(self, cli_group, group_name, expected):
        group = cli_group.commands[group_name]
        registered = set(group.commands)
        missing = expected - registered
        assert not missing, f"Missing {group_name} subcommands: {missing}"


# ---------------------------------------------------------------------------
# (b) Pydantic model public API
# ---------------------------------------------------------------------------

EXPECTED_MODELS = {
    "AccountsConfig",
    "ActionableItem",
    "BirdConfig",
    "CategoryCount",
    "ChartAnalysis",
    "ContextCommand",
    "EnrichmentResult",
    "ExternalLink",
    "FeedTweet",
    "FetchConfig",
    "InlineTweetLink",
    "LLMConfig",
    "LinkNormalizationResult",
    "MediaAnalysisResult",
    "MediaItem",
    "NotificationConfig",
    "PathsConfig",
    "PrimaryPoint",
    "ProcessingConfig",
    "Prompt",
    "QuoteEmbed",
    "Reaction",
    "ScoringConfig",
    "SearchResult",
    "TableAnalysis",
    "TickerCount",
    "TriageResult",
    "TwagConfig",
    "TweetData",
    "TweetLink",
    "TweetListResponse",
    "TweetResponse",
    "VisionResult",
    "XArticleSummaryResult",
}


class TestModelsPublicAPI:
    def test_all_models_exported(self):
        import twag.models

        exported = set(twag.models.__all__)
        missing = EXPECTED_MODELS - exported
        assert not missing, f"Missing model exports: {missing}"


# ---------------------------------------------------------------------------
# (c) DB public API
# ---------------------------------------------------------------------------

EXPECTED_DB_EXPORTS = {
    "DEFAULT_PROMPTS",
    "EQUITY_KEYWORDS",
    "FTS_SCHEMA",
    "SCHEMA",
    "ContextCommand",
    "FeedTweet",
    "Prompt",
    "Reaction",
    "SearchResult",
    "_filter_fts_from_sql",
    "_get_et_offset",
    "_is_fts_statement",
    "apply_account_decay",
    "archive_stale_narratives",
    "boost_account",
    "delete_context_command",
    "delete_reaction",
    "demote_account",
    "dump_sql",
    "get_accounts",
    "get_active_narratives",
    "get_all_context_commands",
    "get_all_prompts",
    "get_authors_to_promote",
    "get_bookmark_counts_by_author",
    "get_connection",
    "get_context_command",
    "get_feed_tweets",
    "get_last_fetch",
    "get_market_day_cutoff",
    "get_processed_counts",
    "get_prompt",
    "get_prompt_history",
    "get_reactions_for_tweet",
    "get_reactions_summary",
    "get_reactions_with_tweets",
    "get_tweet_by_id",
    "get_tweet_stats",
    "get_tweets_by_ids",
    "get_tweets_for_digest",
    "get_unprocessed_tweets",
    "init_db",
    "insert_reaction",
    "insert_tweet",
    "is_tweet_seen",
    "link_tweet_narrative",
    "log_fetch",
    "mark_tweet_bookmarked",
    "mark_tweet_in_digest",
    "migrate_seen_json",
    "mute_account",
    "parse_time_range",
    "promote_account",
    "prune_old_tweets",
    "query_suggests_equity_context",
    "rebuild_fts",
    "restore_sql",
    "rollback_prompt",
    "search_tweets",
    "seed_prompts",
    "toggle_context_command",
    "update_account_last_fetched",
    "update_account_stats",
    "update_tweet_analysis",
    "update_tweet_article",
    "update_tweet_enrichment",
    "update_tweet_links_expanded",
    "update_tweet_processing",
    "upsert_account",
    "upsert_context_command",
    "upsert_narrative",
    "upsert_prompt",
}


class TestDBPublicAPI:
    def test_all_db_symbols_exported(self):
        import twag.db

        exported = set(twag.db.__all__)
        missing = EXPECTED_DB_EXPORTS - exported
        assert not missing, f"Missing db exports: {missing}"


# ---------------------------------------------------------------------------
# (d) Scorer public API
# ---------------------------------------------------------------------------

EXPECTED_SCORER_EXPORTS = {
    "EnrichmentResult",
    "MediaAnalysisResult",
    "TriageResult",
    "VisionResult",
    "XArticleSummaryResult",
    "_call_llm",
    "_call_llm_vision",
    "_parse_json_response",
    "analyze_image",
    "analyze_media",
    "enrich_tweet",
    "get_anthropic_client",
    "get_gemini_client",
    "summarize_document_text",
    "summarize_tweet",
    "summarize_x_article",
    "triage_tweet",
    "triage_tweets_batch",
}


class TestScorerPublicAPI:
    def test_all_scorer_symbols_exported(self):
        import twag.scorer

        exported = set(twag.scorer.__all__)
        missing = EXPECTED_SCORER_EXPORTS - exported
        assert not missing, f"Missing scorer exports: {missing}"


# ---------------------------------------------------------------------------
# (e) DB schema columns
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {
    "tweets": {
        "id",
        "author_handle",
        "author_name",
        "content",
        "created_at",
        "first_seen_at",
        "source",
        "processed_at",
        "relevance_score",
        "category",
        "summary",
        "content_summary",
        "signal_tier",
        "tickers",
        "analysis_json",
        "has_quote",
        "quote_tweet_id",
        "in_reply_to_tweet_id",
        "conversation_id",
        "has_media",
        "media_analysis",
        "media_items",
        "has_link",
        "links_json",
        "link_summary",
        "is_x_article",
        "article_title",
        "article_preview",
        "article_text",
        "article_summary_short",
        "article_primary_points_json",
        "article_action_items_json",
        "article_top_visual_json",
        "article_processed_at",
        "links_expanded_at",
        "quote_reprocessed_at",
        "is_retweet",
        "retweeted_by_handle",
        "retweeted_by_name",
        "original_tweet_id",
        "original_author_handle",
        "original_author_name",
        "original_content",
        "included_in_digest",
        "bookmarked",
        "bookmarked_at",
    },
    "accounts": {
        "handle",
        "display_name",
        "tier",
        "weight",
        "category",
        "tweets_seen",
        "tweets_kept",
        "avg_relevance_score",
        "last_high_signal_at",
        "last_fetched_at",
        "added_at",
        "auto_promoted",
        "muted",
    },
    "reactions": {"id", "tweet_id", "reaction_type", "reason", "target", "created_at"},
    "prompts": {"id", "name", "template", "version", "updated_at", "updated_by"},
    "context_commands": {"id", "name", "command_template", "description", "enabled", "created_at"},
    "narratives": {
        "id",
        "name",
        "first_seen_at",
        "last_mentioned_at",
        "mention_count",
        "sentiment",
        "related_tickers",
        "active",
    },
}


class TestDBSchema:
    @pytest.fixture()
    def db_path(self, tmp_path):
        from twag.db import init_db

        path = tmp_path / "test_compat.db"
        init_db(path)
        return path

    @pytest.mark.parametrize("table_name,expected_cols", list(EXPECTED_TABLES.items()))
    def test_table_columns(self, db_path, table_name, expected_cols):
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        actual_cols = {row[1] for row in cursor.fetchall()}
        conn.close()
        missing = expected_cols - actual_cols
        assert not missing, f"Table '{table_name}' missing columns: {missing}"


# ---------------------------------------------------------------------------
# (f) Web API route inventory
# ---------------------------------------------------------------------------

EXPECTED_ROUTES = {
    "/api/tweets",
    "/api/tweets/{tweet_id}",
    "/api/categories",
    "/api/tickers",
    "/api/react",
    "/api/reactions/{tweet_id}",
    "/api/reactions/{reaction_id}",
    "/api/reactions/summary",
    "/api/reactions/export",
    "/api/prompts",
    "/api/prompts/{name}",
    "/api/prompts/{name}/history",
    "/api/prompts/{name}/rollback",
    "/api/prompts/tune",
    "/api/prompts/{name}/apply-suggestion",
    "/api/context-commands",
    "/api/context-commands/{name}",
    "/api/context-commands/{name}/toggle",
    "/api/context-commands/{name}/test",
    "/api/analyze/{tweet_id}",
}


class TestWebAPIRoutes:
    @pytest.fixture()
    def app(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))
        from twag.web.app import create_app

        return create_app()

    def test_all_expected_routes_registered(self, app):
        registered = {route.path for route in app.routes}
        missing = EXPECTED_ROUTES - registered
        assert not missing, f"Missing API routes: {missing}"


# ---------------------------------------------------------------------------
# (g) Deprecated config aliases emit warnings
# ---------------------------------------------------------------------------


class TestDeprecatedConfigAliases:
    def test_get_memory_dir_warns(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))
        from twag.config import get_memory_dir

        with pytest.warns(DeprecationWarning, match="get_data_dir"):
            get_memory_dir()

    def test_get_workspace_path_warns(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))
        from twag.config import get_workspace_path

        with pytest.warns(DeprecationWarning, match="get_data_dir"):
            get_workspace_path()
