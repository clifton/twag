"""Verify backward-compatibility shims for APIs removed in v0.2.

Each test imports the removed symbol from its old location and asserts that
(a) the import succeeds, (b) a DeprecationWarning is emitted, and
(c) the returned object is usable or delegates correctly.
"""

from __future__ import annotations

import warnings

import pytest

# ---------------------------------------------------------------------------
# twag.config: get_memory_dir, get_workspace_path
# ---------------------------------------------------------------------------


class TestConfigShims:
    def test_get_memory_dir_warns_and_delegates(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))
        from twag.config import get_memory_dir

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = get_memory_dir()
        assert result == tmp_path
        assert any("get_memory_dir" in str(x.message) for x in w)
        assert any(issubclass(x.category, DeprecationWarning) for x in w)

    def test_get_workspace_path_warns_and_delegates(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TWAG_DATA_DIR", str(tmp_path))
        from twag.config import get_workspace_path

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = get_workspace_path()
        assert result == tmp_path
        assert any("get_workspace_path" in str(x.message) for x in w)
        assert any(issubclass(x.category, DeprecationWarning) for x in w)


# ---------------------------------------------------------------------------
# twag.scorer: VisionResult, triage_tweet
# ---------------------------------------------------------------------------


class TestScorerShims:
    def test_vision_result_alias(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from twag.scorer import VisionResult

        from twag.scorer import MediaAnalysisResult

        assert VisionResult is MediaAnalysisResult
        assert any("VisionResult" in str(x.message) for x in w)

    def test_triage_tweet_is_callable(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from twag.scorer import triage_tweet

        assert callable(triage_tweet)
        assert any("triage_tweet" in str(x.message) for x in w)


# ---------------------------------------------------------------------------
# twag.processor: run_full_cycle
# ---------------------------------------------------------------------------


class TestProcessorShims:
    def test_run_full_cycle_is_callable(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from twag.processor import run_full_cycle

        assert callable(run_full_cycle)
        assert any("run_full_cycle" in str(x.message) for x in w)


# ---------------------------------------------------------------------------
# twag.web.tweet_utils: extract_tweet_links, remove_tweet_links,
#                        parse_tweet_id_from_url
# ---------------------------------------------------------------------------


class TestWebTweetUtilsShims:
    def test_extract_tweet_links_warns(self):
        from twag.web.tweet_utils import extract_tweet_links

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = extract_tweet_links(
                "Check https://x.com/user/status/12345 out",
            )

        assert result == [("12345", "https://x.com/user/status/12345")]
        assert any("extract_tweet_links" in str(x.message) for x in w)

    def test_remove_tweet_links_warns(self):
        from twag.web.tweet_utils import remove_tweet_links

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = remove_tweet_links(
                "See https://x.com/u/status/111 here",
                [("111", "https://x.com/u/status/111")],
                {"111"},
            )

        assert "https://x.com" not in result
        assert any("remove_tweet_links" in str(x.message) for x in w)

    def test_parse_tweet_id_from_url_warns(self):
        from twag.web.tweet_utils import parse_tweet_id_from_url

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = parse_tweet_id_from_url(
                "https://twitter.com/user/status/99999",
            )

        assert result == "99999"
        assert any("parse_tweet_id_from_url" in str(x.message) for x in w)

    def test_parse_tweet_id_from_url_none(self):
        from twag.web.tweet_utils import parse_tweet_id_from_url

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert parse_tweet_id_from_url(None) is None


# ---------------------------------------------------------------------------
# twag.models: shim package
# ---------------------------------------------------------------------------


class TestModelsShim:
    def test_direct_re_exports(self):
        """Symbols that map to real dataclasses import without warning."""
        from twag.models import (
            EnrichmentResult,
            LinkNormalizationResult,
            MediaAnalysisResult,
            TriageResult,
            XArticleSummaryResult,
        )

        assert EnrichmentResult is not None
        assert MediaAnalysisResult is not None
        assert TriageResult is not None
        assert XArticleSummaryResult is not None
        assert LinkNormalizationResult is not None

    def test_vision_result_warns(self):
        import twag.models

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            VR = twag.models.VisionResult

        from twag.scorer import MediaAnalysisResult

        assert VR is MediaAnalysisResult
        assert any("VisionResult" in str(x.message) for x in w)

    def test_removed_symbol_raises(self):
        import twag.models

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with pytest.raises(AttributeError, match=r"removed in v0\.2"):
                _ = twag.models.TweetData

    def test_unknown_attr_raises(self):
        import twag.models

        with pytest.raises(AttributeError, match="no attribute"):
            _ = twag.models.CompletelyBogusName


# ---------------------------------------------------------------------------
# API surface snapshots — catch accidental removals from __all__
# ---------------------------------------------------------------------------


class TestAPISurface:
    def test_scorer_all_contains_expected(self):
        import twag.scorer

        expected = {
            "EnrichmentResult",
            "MediaAnalysisResult",
            "TriageResult",
            "XArticleSummaryResult",
            "triage_tweets_batch",
            "enrich_tweet",
            "analyze_media",
            "analyze_image",
            "summarize_tweet",
            "summarize_document_text",
            "summarize_x_article",
            # compat shims
            "VisionResult",
            "triage_tweet",
        }
        assert expected <= set(twag.scorer.__all__)

    def test_processor_all_contains_expected(self):
        import twag.processor

        expected = {
            "process_unprocessed",
            "enrich_high_signal",
            "reprocess_today_quoted",
            "fetch_and_store",
            "fetch_and_store_bookmarks",
            "ensure_media_analysis",
            # compat shim
            "run_full_cycle",
        }
        assert expected <= set(twag.processor.__all__)
