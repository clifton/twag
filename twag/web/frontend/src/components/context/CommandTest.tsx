import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Play, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { useTestContextCommand } from "@/hooks/use-context-commands";
import type { CommandTestResult, ContextCommand } from "@/api/types";

interface CommandTestProps {
  command: ContextCommand;
  onClose: () => void;
}

export function CommandTest({ command, onClose }: CommandTestProps) {
  const [tweetId, setTweetId] = useState("");
  const [result, setResult] = useState<CommandTestResult | null>(null);
  const test = useTestContextCommand();

  const handleTest = () => {
    if (!tweetId.trim()) return;
    test.mutate(
      { name: command.name, tweetId: tweetId.trim() },
      {
        onSuccess: setResult,
      },
    );
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-mono text-sm">
            Test: {command.name}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex gap-2">
            <Input
              value={tweetId}
              onChange={(e) => setTweetId(e.target.value)}
              placeholder="Tweet ID"
              className="font-mono flex-1"
              onKeyDown={(e) => e.key === "Enter" && handleTest()}
            />
            <Button
              size="sm"
              onClick={handleTest}
              disabled={!tweetId.trim() || test.isPending}
            >
              {test.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Play className="h-3 w-3" />
              )}
              Run
            </Button>
          </div>

          {result && (
            <div className="space-y-2">
              {/* Status */}
              <div className="flex items-center gap-2">
                {result.success ? (
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                ) : (
                  <XCircle className="h-4 w-4 text-red-400" />
                )}
                <span className="text-xs text-zinc-400">
                  Exit code: {result.returncode}
                </span>
              </div>

              {/* Final command */}
              <div>
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-0.5">
                  Command
                </div>
                <div className="rounded border border-zinc-800 bg-zinc-950 p-2">
                  <code className="text-xs text-zinc-400 font-mono break-all">
                    {result.final_command}
                  </code>
                </div>
              </div>

              {/* Variables */}
              {result.variables_used && Object.keys(result.variables_used).length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {Object.entries(result.variables_used).map(([k, v]) => (
                    <Badge key={k} variant="outline" className="text-[10px] font-mono">
                      {k}={v || "(empty)"}
                    </Badge>
                  ))}
                </div>
              )}

              {/* Output */}
              {result.stdout && (
                <div>
                  <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-0.5">
                    stdout
                  </div>
                  <div className="rounded border border-zinc-800 bg-zinc-950 p-2 max-h-48 overflow-y-auto">
                    <pre className="text-xs text-zinc-400 font-mono whitespace-pre-wrap">
                      {result.stdout}
                    </pre>
                  </div>
                </div>
              )}

              {result.stderr && (
                <div>
                  <div className="text-[10px] text-red-500/70 uppercase tracking-wider mb-0.5">
                    stderr
                  </div>
                  <div className="rounded border border-red-900/30 bg-red-950/20 p-2 max-h-48 overflow-y-auto">
                    <pre className="text-xs text-red-400/70 font-mono whitespace-pre-wrap">
                      {result.stderr}
                    </pre>
                  </div>
                </div>
              )}

              {result.error && (
                <div className="text-xs text-red-400">{result.error}</div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
