"""Backward-compatibility guardrail tests.

Ensures public API surface remains stable across changes:
- All symbols in twag/models __all__ are importable
- Deprecated config functions emit DeprecationWarning
- No private (_-prefixed) symbols leak into package __all__ exports
- TweetResponse model fields cover what the /tweets/{id} route returns
"""

import importlib
import warnings

import pytest


class TestModelsAllImportable:
    """Every symbol advertised in twag.models.__all__ must be importable."""

    def test_all_symbols_importable(self):
        import twag.models as models

        for name in models.__all__:
            obj = getattr(models, name, None)
            assert obj is not None, f"twag.models.__all__ advertises '{name}' but it is not importable"


class TestDeprecationWarnings:
    """Legacy config aliases must emit DeprecationWarning at call time."""

    def test_get_memory_dir_warns(self):
        from twag.config import get_memory_dir

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            get_memory_dir()
            deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecations) == 1
            assert "get_memory_dir" in str(deprecations[0].message)

    def test_get_workspace_path_warns(self):
        from twag.config import get_workspace_path

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            get_workspace_path()
            deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecations) == 1
            assert "get_workspace_path" in str(deprecations[0].message)

    def test_deprecated_functions_still_work(self):
        """Deprecated functions must still return the same value as their replacement."""
        from twag.config import get_data_dir, get_memory_dir, get_workspace_path

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert get_memory_dir() == get_data_dir()
            assert get_workspace_path() == get_data_dir()


class TestNoPrivateSymbolsInAll:
    """No package __all__ should advertise underscore-prefixed symbols."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "twag.models",
            "twag.db",
            "twag.processor",
            "twag.scorer",
        ],
    )
    def test_no_private_in_all(self, module_path):
        mod = importlib.import_module(module_path)
        all_names = getattr(mod, "__all__", [])
        private = [name for name in all_names if name.startswith("_")]
        assert private == [], f"{module_path}.__all__ exposes private symbols: {private}"


class TestTweetResponseCoversRouteKeys:
    """TweetResponse model fields must be a superset of the /tweets/{id} route keys."""

    def test_response_model_covers_route_keys(self):
        from twag.models.api import TweetResponse

        # All keys returned by the GET /tweets/{tweet_id} route handler
        route_keys = {
            "id",
            "author_handle",
            "author_name",
            "content",
            "content_summary",
            "summary",
            "created_at",
            "relevance_score",
            "categories",
            "signal_tier",
            "tickers",
            "bookmarked",
            "has_quote",
            "quote_tweet_id",
            "has_media",
            "media_analysis",
            "media_items",
            "has_link",
            "link_summary",
            "is_x_article",
            "article_title",
            "article_preview",
            "article_text",
            "article_summary_short",
            "article_primary_points",
            "article_action_items",
            "article_top_visual",
            "article_processed_at",
            "is_retweet",
            "retweeted_by_handle",
            "retweeted_by_name",
            "original_tweet_id",
            "original_author_handle",
            "original_author_name",
            "original_content",
            "links_json",
        }

        model_fields = set(TweetResponse.model_fields.keys())
        missing = route_keys - model_fields
        assert missing == set(), f"TweetResponse is missing fields returned by the route: {missing}"
