import { useState } from "react";
import { FileText, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { usePrompts } from "@/hooks/use-prompts";
import { PromptEditor } from "./PromptEditor";
import { PromptHistory } from "./PromptHistory";
import { TuningSuggestion } from "./TuningSuggestion";

export function PromptsPage() {
  const { data, isLoading } = usePrompts();
  const [selected, setSelected] = useState<string | null>(null);

  const prompts = data?.prompts ?? [];
  const activePrompt = prompts.find((p) => p.name === selected) ?? prompts[0];

  // Auto-select first prompt
  if (!selected && prompts.length > 0 && activePrompt) {
    setSelected(activePrompt.name);
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-zinc-600" />
      </div>
    );
  }

  if (prompts.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-zinc-500">
        No prompts configured. Process some tweets first.
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Left sidebar: prompt list + tools */}
      <div className="w-64 shrink-0 border-r border-zinc-800 flex flex-col">
        <div className="border-b border-zinc-800 px-3 py-2">
          <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
            Prompts
          </span>
        </div>

        {/* Prompt list */}
        <div className="flex-1 overflow-y-auto">
          {prompts.map((p) => (
            <button
              key={p.name}
              onClick={() => setSelected(p.name)}
              className={cn(
                "flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors",
                p.name === activePrompt?.name
                  ? "bg-zinc-800/70 text-zinc-100"
                  : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300",
              )}
            >
              <FileText className="h-3.5 w-3.5 shrink-0" />
              <div className="min-w-0">
                <div className="truncate font-mono text-xs">{p.name}</div>
                <div className="text-[10px] text-zinc-600">
                  v{p.version} &middot; {p.updated_by}
                </div>
              </div>
            </button>
          ))}
        </div>

        {/* History + Tuning panel */}
        {activePrompt && (
          <div className="border-t border-zinc-800">
            <div className="px-3 py-2">
              <span className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">
                History
              </span>
            </div>
            <div className="max-h-40 overflow-y-auto px-1">
              <PromptHistory
                name={activePrompt.name}
                currentVersion={activePrompt.version}
              />
            </div>
            <div className="border-t border-zinc-800 p-3">
              <TuningSuggestion promptName={activePrompt.name} />
            </div>
          </div>
        )}
      </div>

      {/* Right: editor */}
      <div className="flex-1">
        {activePrompt ? (
          <PromptEditor prompt={activePrompt} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-zinc-500">
            Select a prompt
          </div>
        )}
      </div>
    </div>
  );
}
