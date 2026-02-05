import { useInfiniteQuery } from "@tanstack/react-query";
import { fetchTweets } from "@/api/tweets";
import type { FeedFilters } from "@/api/types";

const PAGE_SIZE = 50;

export function useTweets(filters: FeedFilters) {
  return useInfiniteQuery({
    queryKey: ["tweets", filters],
    queryFn: ({ pageParam = 0 }) => fetchTweets(filters, PAGE_SIZE, pageParam),
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.offset + lastPage.limit : undefined,
    initialPageParam: 0,
  });
}
