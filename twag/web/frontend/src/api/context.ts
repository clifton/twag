import { del, get, post, put } from "./client";
import type {
  CommandTestResult,
  ContextCommand,
  ContextCommandCreate,
  ContextCommandsResponse,
} from "./types";

export function fetchContextCommands(
  enabledOnly = false,
): Promise<ContextCommandsResponse> {
  return get<ContextCommandsResponse>("/api/context-commands", {
    enabled_only: enabledOnly,
  });
}

export function fetchContextCommand(name: string): Promise<ContextCommand> {
  return get<ContextCommand>(`/api/context-commands/${name}`);
}

export function createContextCommand(command: ContextCommandCreate) {
  return post<{ id: number; name: string; message: string }>(
    "/api/context-commands",
    command,
  );
}

export function updateContextCommand(
  name: string,
  command: ContextCommandCreate,
) {
  return put<{ id: number; name: string; message: string }>(
    `/api/context-commands/${name}`,
    command,
  );
}

export function deleteContextCommand(name: string) {
  return del<{ message: string }>(`/api/context-commands/${name}`);
}

export function toggleContextCommand(name: string, enabled: boolean) {
  return post<{ message: string }>(
    `/api/context-commands/${name}/toggle?enabled=${enabled}`,
  );
}

export function testContextCommand(
  name: string,
  tweetId: string,
): Promise<CommandTestResult> {
  return post<CommandTestResult>(`/api/context-commands/${name}/test`, {
    tweet_id: tweetId,
  });
}
