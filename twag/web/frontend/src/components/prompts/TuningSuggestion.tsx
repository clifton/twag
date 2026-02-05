import { useState } from "react";
import { Sparkles, Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTunePrompt, useApplySuggestion } from "@/hooks/use-prompts";
import { toast } from "@/components/ui/toaster";
import type { TuneResponse } from "@/api/types";

interface TuningSuggestionProps {
  promptName: string;
}

export function TuningSuggestion({ promptName }: TuningSuggestionProps) {
  const [result, setResult] = useState<TuneResponse | null>(null);
  const tune = useTunePrompt();
  const apply = useApplySuggestion();

  const handleTune = () => {
    tune.mutate(promptName, {
      onSuccess: (data) => {
        if (data.error) {
          toast(data.error, "error");
        } else {
          setResult(data);
        }
      },
      onError: () => toast("Tuning failed", "error"),
    });
  };

  const handleApply = () => {
    if (!result?.suggested_prompt) return;
    apply.mutate(
      { name: promptName, template: result.suggested_prompt },
      {
        onSuccess: () => {
          toast("Suggestion applied", "success");
          setResult(null);
        },
        onError: () => toast("Failed to apply suggestion", "error"),
      },
    );
  };

  return (
    <div className="space-y-3">
      <Button
        variant="outline"
        size="sm"
        onClick={handleTune}
        disabled={tune.isPending}
        className="w-full"
      >
        {tune.isPending ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <Sparkles className="h-3 w-3" />
        )}
        Tune with reactions
      </Button>

      {result && (
        <div className="space-y-2">
          {result.reactions_analyzed && (
            <div className="flex gap-3 text-[10px] text-zinc-500 font-mono">
              <span>
                &gt;&gt; {result.reactions_analyzed.high_importance}
              </span>
              <span>
                &gt; {result.reactions_analyzed.should_be_higher}
              </span>
              <span>
                &lt; {result.reactions_analyzed.less_important}
              </span>
            </div>
          )}

          {result.analysis && (
            <div className="rounded border border-zinc-800 bg-zinc-900/50 p-2 text-xs text-zinc-400 leading-relaxed max-h-40 overflow-y-auto">
              {result.analysis}
            </div>
          )}

          {result.suggested_prompt && (
            <div className="space-y-1.5">
              <div className="rounded border border-zinc-800 bg-zinc-900/50 p-2 text-xs font-mono text-zinc-400 leading-relaxed max-h-48 overflow-y-auto">
                <pre className="whitespace-pre-wrap">{result.suggested_prompt}</pre>
              </div>
              <Button
                size="sm"
                onClick={handleApply}
                disabled={apply.isPending}
                className="w-full"
              >
                {apply.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Check className="h-3 w-3" />
                )}
                Apply suggestion
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
