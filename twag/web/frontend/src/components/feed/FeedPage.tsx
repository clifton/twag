import { useEffect, useRef, useCallback } from "react";
import { Loader2 } from "lucide-react";
import { FilterBar } from "@/components/layout/FilterBar";
import { TweetCard } from "./TweetCard";
import { Skeleton } from "@/components/ui/skeleton";
import { useTweets } from "@/hooks/use-tweets";
import { useFilterState } from "@/hooks/use-filter-state";

function TweetSkeleton() {
  return (
    <div className="border-b border-zinc-800/40 px-4 py-3">
      <Skeleton className="h-3 w-40" />
      <div className="mt-2 space-y-1.5">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
      <div className="mt-2.5 flex items-center justify-between">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-3 w-16" />
      </div>
    </div>
  );
}

export function FeedPage() {
  const { filters, setFilter, clearFilters, activeFilterCount } = useFilterState();
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
  } = useTweets(filters);

  const sentinelRef = useRef<HTMLDivElement>(null);

  const handleIntersect = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const entry = entries[0];
      if (entry?.isIntersecting && hasNextPage && !isFetchingNextPage) {
        fetchNextPage();
      }
    },
    [fetchNextPage, hasNextPage, isFetchingNextPage],
  );

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(handleIntersect, {
      rootMargin: "400px",
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [handleIntersect]);

  const tweets = data?.pages.flatMap((p) => p.tweets) ?? [];

  return (
    <div className="flex h-full flex-col">
      <FilterBar
        filters={filters}
        setFilter={setFilter}
        clearFilters={clearFilters}
        activeFilterCount={activeFilterCount}
      />

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl">
          {isLoading && (
            <div>
              {Array.from({ length: 8 }).map((_, i) => (
                <TweetSkeleton key={i} />
              ))}
            </div>
          )}

          {isError && (
            <div className="flex items-center justify-center py-16 text-sm text-red-400">
              Failed to load tweets. Is the API running?
            </div>
          )}

          {!isLoading && tweets.length === 0 && (
            <div className="flex items-center justify-center py-16 text-sm text-zinc-300">
              No tweets match your filters
            </div>
          )}

          {tweets.map((tweet) => (
            <TweetCard key={tweet.id} tweet={tweet} />
          ))}
        </div>

        {/* Sentinel for infinite scroll */}
        <div ref={sentinelRef} className="h-1" />

        {isFetchingNextPage && (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
          </div>
        )}

        {!hasNextPage && tweets.length > 0 && (
          <div className="py-4 text-center text-xs text-zinc-400">
            End of feed
          </div>
        )}
      </div>
    </div>
  );
}
