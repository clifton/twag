"""Tweet processing pipeline."""

from .dependencies import (
    _ensure_quote_row,
    _expand_links_for_rows,
    _expand_single_tweet_links,
    _expand_unprocessed_with_dependencies,
    _extract_dependency_ids_from_row,
    _extract_inline_linked_tweet_ids,
    _extract_inline_linked_tweet_ids_from_links_json,
    _fetch_inline_linked_tweets,
    _fetch_quote_by_id,
    _fetch_quote_chain,
    _fetch_reply_chain,
    _row_get,
)
from .pipeline import (
    enrich_high_signal,
    process_unprocessed,
    reprocess_today_quoted,
)
from .storage import (
    auto_promote_bookmarked_authors,
    fetch_and_store,
    fetch_and_store_bookmarks,
    store_bookmarked_tweets,
    store_fetched_tweets,
)
from .triage import (
    _analyze_media_items,
    _build_triage_text,
    _merge_document_media,
    _needs_media_analysis,
    _normalized_worker_count,
    _page_number_hint,
    _prefer_stronger_signal_tier,
    _select_article_top_visual,
    _tokenize_for_overlap,
    _triage_rows,
    ensure_media_analysis,
)

__all__ = [
    "_analyze_media_items",
    "_build_triage_text",
    "_ensure_quote_row",
    "_expand_links_for_rows",
    "_expand_single_tweet_links",
    "_expand_unprocessed_with_dependencies",
    "_extract_dependency_ids_from_row",
    "_extract_inline_linked_tweet_ids",
    "_extract_inline_linked_tweet_ids_from_links_json",
    "_fetch_inline_linked_tweets",
    "_fetch_quote_by_id",
    "_fetch_quote_chain",
    "_fetch_reply_chain",
    "_merge_document_media",
    "_needs_media_analysis",
    "_normalized_worker_count",
    "_page_number_hint",
    "_prefer_stronger_signal_tier",
    "_row_get",
    "_select_article_top_visual",
    "_tokenize_for_overlap",
    "_triage_rows",
    "auto_promote_bookmarked_authors",
    "enrich_high_signal",
    "ensure_media_analysis",
    "fetch_and_store",
    "fetch_and_store_bookmarks",
    "process_unprocessed",
    "reprocess_today_quoted",
    "run_full_cycle",
    "store_bookmarked_tweets",
    "store_fetched_tweets",
]


def __getattr__(name: str):
    if name == "run_full_cycle":
        from twag._compat import _deprecated

        _deprecated(
            "twag.processor.run_full_cycle",
            "twag.processor.process_unprocessed + twag.processor.enrich_high_signal",
        )

        def run_full_cycle(
            fetch_home: bool = True,
            fetch_tier1: bool = True,
            process: bool = True,
            enrich: bool = True,
        ) -> dict:
            """Deprecated orchestrator — use process_unprocessed + enrich_high_signal."""
            from twag.db import get_accounts, get_connection

            stats: dict = {
                "home_fetched": 0,
                "home_new": 0,
                "tier1_fetched": 0,
                "tier1_new": 0,
                "processed": 0,
                "enriched": 0,
            }
            if fetch_home:
                fetched, new = fetch_and_store(source="home", count=100)
                stats["home_fetched"] = fetched
                stats["home_new"] = new
            if fetch_tier1:
                with get_connection() as conn:
                    tier1 = get_accounts(conn, tier=1)
                for account in tier1:
                    try:
                        fetched, new = fetch_and_store(
                            source="user",
                            handle=account["handle"],
                            count=20,
                        )
                        stats["tier1_fetched"] += fetched
                        stats["tier1_new"] += new
                    except Exception:
                        pass
            if process:
                results = process_unprocessed(limit=100)
                stats["processed"] = len(results)
            if enrich:
                results = enrich_high_signal(limit=20)
                stats["enriched"] = len(results)
            return stats

        return run_full_cycle

    raise AttributeError(f"module 'twag.processor' has no attribute {name!r}")
