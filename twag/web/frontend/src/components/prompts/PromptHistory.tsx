import { Clock, Loader2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import { usePromptHistory, useRollbackPrompt } from "@/hooks/use-prompts";

interface PromptHistoryProps {
  name: string;
  currentVersion: number;
}

export function PromptHistory({ name, currentVersion }: PromptHistoryProps) {
  const { data, isLoading } = usePromptHistory(name);
  const rollback = useRollbackPrompt();

  const handleRollback = (version: number) => {
    rollback.mutate(
      { name, version },
      {
        onSuccess: () => toast(`Rolled back to v${version}`, "success"),
        onError: () => toast("Rollback failed", "error"),
      },
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8 text-zinc-600">
        <Loader2 className="h-4 w-4 animate-spin" />
      </div>
    );
  }

  const history = data?.history ?? [];

  if (history.length === 0) {
    return (
      <div className="py-4 text-center text-xs text-zinc-600">
        No version history
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      {history.map((entry) => (
        <div
          key={entry.version}
          className="flex items-center justify-between px-3 py-1.5 hover:bg-zinc-800/50 rounded"
        >
          <div className="flex items-center gap-2">
            <Clock className="h-3 w-3 text-zinc-600" />
            <span className="font-mono text-xs text-zinc-400">
              v{entry.version}
            </span>
            <span className="text-[10px] text-zinc-600">
              {entry.updated_by}
            </span>
            <span className="text-[10px] text-zinc-600">
              {new Date(entry.updated_at).toLocaleDateString()}
            </span>
          </div>
          {entry.version !== currentVersion && (
            <Button
              variant="ghost"
              size="sm"
              className="h-5 text-[10px] text-zinc-500"
              onClick={() => handleRollback(entry.version)}
              disabled={rollback.isPending}
            >
              {rollback.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <RotateCcw className="h-3 w-3" />
              )}
              Rollback
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}
