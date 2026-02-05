import { get, post, put } from "./client";
import type {
  Prompt,
  PromptHistory,
  PromptsResponse,
  TuneResponse,
} from "./types";

export function fetchPrompts(): Promise<PromptsResponse> {
  return get<PromptsResponse>("/api/prompts");
}

export function fetchPrompt(name: string): Promise<Prompt> {
  return get<Prompt>(`/api/prompts/${name}`);
}

export function updatePrompt(
  name: string,
  template: string,
  updatedBy = "user",
) {
  return put<{ name: string; version: number; message: string }>(
    `/api/prompts/${name}`,
    { template, updated_by: updatedBy },
  );
}

export function fetchPromptHistory(
  name: string,
  limit = 10,
): Promise<PromptHistory> {
  return get<PromptHistory>(`/api/prompts/${name}/history`, { limit });
}

export function rollbackPrompt(name: string, version: number) {
  return post<{ message: string }>(`/api/prompts/${name}/rollback?version=${version}`);
}

export function tunePrompt(promptName: string, reactionLimit = 50) {
  return post<TuneResponse>("/api/prompts/tune", {
    prompt_name: promptName,
    reaction_limit: reactionLimit,
  });
}

export function applySuggestion(name: string, template: string) {
  return post<{ name: string; version: number; message: string }>(
    `/api/prompts/${name}/apply-suggestion`,
    { template, updated_by: "llm" },
  );
}
