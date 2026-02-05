import { useState, useEffect } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { markdown } from "@codemirror/lang-markdown";
import { oneDark } from "@codemirror/theme-one-dark";
import { EditorView } from "@codemirror/view";
import { Button } from "@/components/ui/button";
import { Save, RotateCcw, Loader2 } from "lucide-react";
import { useUpdatePrompt } from "@/hooks/use-prompts";
import { toast } from "@/components/ui/toaster";
import type { Prompt } from "@/api/types";

interface PromptEditorProps {
  prompt: Prompt;
}

const darkTheme = EditorView.theme({
  "&": { backgroundColor: "#09090b", fontSize: "13px" },
  ".cm-gutters": { backgroundColor: "#09090b", borderRight: "1px solid #27272a" },
  ".cm-activeLineGutter": { backgroundColor: "#18181b" },
  ".cm-activeLine": { backgroundColor: "#18181b50" },
});

export function PromptEditor({ prompt }: PromptEditorProps) {
  const [value, setValue] = useState(prompt.template);
  const [dirty, setDirty] = useState(false);
  const updatePrompt = useUpdatePrompt();

  useEffect(() => {
    setValue(prompt.template);
    setDirty(false);
  }, [prompt.template, prompt.version]);

  const handleChange = (val: string) => {
    setValue(val);
    setDirty(val !== prompt.template);
  };

  const handleSave = () => {
    updatePrompt.mutate(
      { name: prompt.name, template: value },
      {
        onSuccess: () => {
          setDirty(false);
          toast("Prompt saved", "success");
        },
        onError: () => toast("Failed to save prompt", "error"),
      },
    );
  };

  const handleReset = () => {
    setValue(prompt.template);
    setDirty(false);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-1.5">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm text-zinc-200">{prompt.name}</span>
          <span className="text-[11px] text-zinc-600 font-mono">v{prompt.version}</span>
          {dirty && <span className="text-[10px] text-yellow-500">modified</span>}
        </div>
        <div className="flex items-center gap-1">
          {dirty && (
            <Button variant="ghost" size="sm" onClick={handleReset}>
              <RotateCcw className="h-3 w-3" />
              Reset
            </Button>
          )}
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!dirty || updatePrompt.isPending}
          >
            {updatePrompt.isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Save className="h-3 w-3" />
            )}
            Save
          </Button>
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        <CodeMirror
          value={value}
          onChange={handleChange}
          extensions={[markdown(), darkTheme]}
          theme={oneDark}
          height="100%"
          className="h-full"
          basicSetup={{
            lineNumbers: true,
            foldGutter: false,
            highlightActiveLine: true,
          }}
        />
      </div>
    </div>
  );
}
