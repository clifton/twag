import { Loader2, Plus } from "lucide-react";
import { useState } from "react";
import type { ContextCommand } from "@/api/types";
import { Button } from "@/components/ui/button";
import { useContextCommands } from "@/hooks/use-context-commands";
import { CommandForm } from "./CommandForm";
import { CommandList } from "./CommandList";
import { CommandTest } from "./CommandTest";

export function ContextPage() {
  const { data, isLoading } = useContextCommands();
  const [editing, setEditing] = useState<ContextCommand | null | "new">(null);
  const [testing, setTesting] = useState<ContextCommand | null>(null);

  const commands = data?.commands ?? [];

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-zinc-600" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
          <div>
            <h1 className="text-sm font-medium text-zinc-200">
              Context Commands
            </h1>
            <p className="text-xs text-zinc-500 mt-0.5">
              Shell commands injected into deep analysis as additional context
            </p>
          </div>
          <Button size="sm" onClick={() => setEditing("new")}>
            <Plus className="h-3 w-3" />
            New
          </Button>
        </div>

        {/* Command list */}
        <CommandList
          commands={commands}
          onEdit={setEditing}
          onTest={setTesting}
        />
      </div>

      {/* Edit/Create modal */}
      {editing !== null && (
        <CommandForm
          command={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}

      {/* Test modal */}
      {testing && (
        <CommandTest command={testing} onClose={() => setTesting(null)} />
      )}
    </div>
  );
}
