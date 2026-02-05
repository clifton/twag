import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContextCommand,
  deleteContextCommand,
  fetchContextCommands,
  testContextCommand,
  toggleContextCommand,
  updateContextCommand,
} from "@/api/context";
import type { ContextCommandCreate } from "@/api/types";

export function useContextCommands() {
  return useQuery({
    queryKey: ["context-commands"],
    queryFn: () => fetchContextCommands(),
  });
}

export function useCreateContextCommand() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (command: ContextCommandCreate) =>
      createContextCommand(command),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["context-commands"] });
    },
  });
}

export function useUpdateContextCommand() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      name,
      command,
    }: {
      name: string;
      command: ContextCommandCreate;
    }) => updateContextCommand(name, command),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["context-commands"] });
    },
  });
}

export function useDeleteContextCommand() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => deleteContextCommand(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["context-commands"] });
    },
  });
}

export function useToggleContextCommand() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      toggleContextCommand(name, enabled),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["context-commands"] });
    },
  });
}

export function useTestContextCommand() {
  return useMutation({
    mutationFn: ({ name, tweetId }: { name: string; tweetId: string }) =>
      testContextCommand(name, tweetId),
  });
}
