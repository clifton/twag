import { useMutation, useQueryClient } from "@tanstack/react-query";
import { analyzeTweet, createReaction, deleteReaction } from "@/api/reactions";
import type { ReactionCreate } from "@/api/types";

export function useCreateReaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reaction: ReactionCreate) => createReaction(reaction),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tweets"] });
    },
  });
}

export function useDeleteReaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reactionId: number) => deleteReaction(reactionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tweets"] });
    },
  });
}

export function useAnalyzeTweet() {
  return useMutation({
    mutationFn: (tweetId: string) => analyzeTweet(tweetId),
  });
}
