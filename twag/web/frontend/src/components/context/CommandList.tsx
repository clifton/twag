import { Pencil, Trash2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useToggleContextCommand, useDeleteContextCommand } from "@/hooks/use-context-commands";
import { toast } from "@/components/ui/toaster";
import type { ContextCommand } from "@/api/types";

interface CommandListProps {
  commands: ContextCommand[];
  onEdit: (cmd: ContextCommand) => void;
  onTest: (cmd: ContextCommand) => void;
}

export function CommandList({ commands, onEdit, onTest }: CommandListProps) {
  const toggle = useToggleContextCommand();
  const del = useDeleteContextCommand();

  const handleToggle = (name: string, enabled: boolean) => {
    toggle.mutate(
      { name, enabled },
      {
        onSuccess: () => toast(`${name} ${enabled ? "enabled" : "disabled"}`, "success"),
        onError: () => toast("Toggle failed", "error"),
      },
    );
  };

  const handleDelete = (name: string) => {
    if (!confirm(`Delete command "${name}"?`)) return;
    del.mutate(name, {
      onSuccess: () => toast(`${name} deleted`, "success"),
      onError: () => toast("Delete failed", "error"),
    });
  };

  if (commands.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-zinc-500">
        No context commands yet
      </div>
    );
  }

  return (
    <div className="divide-y divide-zinc-800/50">
      {commands.map((cmd) => (
        <div
          key={cmd.name}
          className="flex items-start gap-3 px-4 py-3 hover:bg-zinc-900/30 transition-colors"
        >
          <Switch
            checked={cmd.enabled}
            onCheckedChange={(checked) => handleToggle(cmd.name, checked)}
            className="mt-0.5"
          />

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-zinc-200">{cmd.name}</span>
            </div>
            {cmd.description && (
              <p className="mt-0.5 text-xs text-zinc-500">{cmd.description}</p>
            )}
            <div className="mt-1 rounded border border-zinc-800 bg-zinc-950 px-2 py-1">
              <code className="text-[11px] text-zinc-500 font-mono break-all">
                {cmd.command_template}
              </code>
            </div>
          </div>

          <div className="flex items-center gap-0.5">
            <Button
              variant="ghost"
              size="sm"
              className="text-xs text-zinc-500"
              onClick={() => onTest(cmd)}
            >
              Test
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-zinc-600 hover:text-zinc-300"
              onClick={() => onEdit(cmd)}
            >
              <Pencil className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-zinc-600 hover:text-red-400"
              onClick={() => handleDelete(cmd.name)}
              disabled={del.isPending}
            >
              {del.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Trash2 className="h-3 w-3" />
              )}
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}
