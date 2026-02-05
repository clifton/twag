import { del, get, post } from "./client";
import type {
  AnalyzeResult,
  ReactionCreate,
  ReactionsResponse,
  ReactionsSummary,
} from "./types";

export function fetchReactions(tweetId: string): Promise<ReactionsResponse> {
  return get<ReactionsResponse>(`/api/reactions/${tweetId}`);
}

export function createReaction(reaction: ReactionCreate) {
  return post<{ id: number; tweet_id?: string; message?: string }>(
    "/api/react",
    reaction,
  );
}

export function deleteReaction(reactionId: number) {
  return del<{ message: string }>(`/api/reactions/${reactionId}`);
}

export function fetchReactionsSummary(): Promise<ReactionsSummary> {
  return get<ReactionsSummary>("/api/reactions/summary");
}

export function analyzeTweet(tweetId: string): Promise<AnalyzeResult> {
  return post<AnalyzeResult>(`/api/analyze/${tweetId}`);
}
