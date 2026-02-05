import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";
import type { FeedFilters } from "@/api/types";

const FILTER_KEYS = [
  "since",
  "min_score",
  "signal_tier",
  "category",
  "ticker",
  "author",
  "bookmarked",
  "sort",
] as const;

export function useFilterState() {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters: FeedFilters = useMemo(() => {
    const f: FeedFilters = {};
    const since = searchParams.get("since");
    if (since) f.since = since;
    const minScore = searchParams.get("min_score");
    if (minScore) f.min_score = Number(minScore);
    const signalTier = searchParams.get("signal_tier");
    if (signalTier) f.signal_tier = signalTier;
    const category = searchParams.get("category");
    if (category) f.category = category;
    const ticker = searchParams.get("ticker");
    if (ticker) f.ticker = ticker;
    const author = searchParams.get("author");
    if (author) f.author = author;
    const bookmarked = searchParams.get("bookmarked");
    if (bookmarked === "true") f.bookmarked = true;
    const sort = searchParams.get("sort");
    if (sort) f.sort = sort;
    return f;
  }, [searchParams]);

  const setFilter = useCallback(
    (key: keyof FeedFilters, value: string | number | boolean | undefined) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value === undefined || value === "" || value === false) {
          next.delete(key);
        } else {
          next.set(key, String(value));
        }
        return next;
      });
    },
    [setSearchParams],
  );

  const clearFilters = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams();
      // Preserve sort
      const sort = prev.get("sort");
      if (sort) next.set("sort", sort);
      return next;
    });
  }, [setSearchParams]);

  const activeFilterCount = useMemo(() => {
    return FILTER_KEYS.filter((k) => {
      if (k === "sort") return false;
      return searchParams.has(k);
    }).length;
  }, [searchParams]);

  return { filters, setFilter, clearFilters, activeFilterCount };
}
