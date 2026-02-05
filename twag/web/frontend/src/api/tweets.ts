import { get } from "./client";
import type {
  CategoriesResponse,
  FeedFilters,
  TickersResponse,
  TweetsResponse,
} from "./types";

export function fetchTweets(
  filters: FeedFilters,
  limit: number,
  offset: number,
): Promise<TweetsResponse> {
  return get<TweetsResponse>("/api/tweets", {
    ...filters,
    limit,
    offset,
  });
}

export function fetchCategories(): Promise<CategoriesResponse> {
  return get<CategoriesResponse>("/api/categories");
}

export function fetchTickers(limit = 50): Promise<TickersResponse> {
  return get<TickersResponse>("/api/tickers", { limit });
}
