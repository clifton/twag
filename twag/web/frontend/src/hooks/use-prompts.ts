import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  applySuggestion,
  fetchPromptHistory,
  fetchPrompts,
  rollbackPrompt,
  tunePrompt,
  updatePrompt,
} from "@/api/prompts";

export function usePrompts() {
  return useQuery({
    queryKey: ["prompts"],
    queryFn: fetchPrompts,
  });
}

export function usePromptHistory(name: string | null) {
  return useQuery({
    queryKey: ["prompt-history", name],
    queryFn: () => fetchPromptHistory(name!, 20),
    enabled: !!name,
  });
}

export function useUpdatePrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, template }: { name: string; template: string }) =>
      updatePrompt(name, template),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prompts"] });
      qc.invalidateQueries({ queryKey: ["prompt-history"] });
    },
  });
}

export function useRollbackPrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, version }: { name: string; version: number }) =>
      rollbackPrompt(name, version),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prompts"] });
      qc.invalidateQueries({ queryKey: ["prompt-history"] });
    },
  });
}

export function useTunePrompt() {
  return useMutation({
    mutationFn: (promptName: string) => tunePrompt(promptName),
  });
}

export function useApplySuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, template }: { name: string; template: string }) =>
      applySuggestion(name, template),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prompts"] });
      qc.invalidateQueries({ queryKey: ["prompt-history"] });
    },
  });
}
