import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { ContextCommand } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toaster";
import {
  useCreateContextCommand,
  useUpdateContextCommand,
} from "@/hooks/use-context-commands";

interface CommandFormProps {
  command: ContextCommand | null; // null = create mode
  onClose: () => void;
}

const VARIABLES = [
  { name: "{tweet_id}", desc: "Tweet ID" },
  { name: "{author}", desc: "Author handle" },
  { name: "{tweet_date}", desc: "YYYY-MM-DD" },
  { name: "{tweet_datetime}", desc: "ISO datetime" },
  { name: "{ticker}", desc: "First ticker" },
  { name: "{tickers}", desc: "Comma-separated tickers" },
];

export function CommandForm({ command, onClose }: CommandFormProps) {
  const [name, setName] = useState("");
  const [template, setTemplate] = useState("");
  const [description, setDescription] = useState("");

  const create = useCreateContextCommand();
  const update = useUpdateContextCommand();
  const isPending = create.isPending || update.isPending;

  useEffect(() => {
    if (command) {
      setName(command.name);
      setTemplate(command.command_template);
      setDescription(command.description ?? "");
    }
  }, [command]);

  const handleSubmit = () => {
    if (!name.trim() || !template.trim()) return;

    const payload = {
      name: name.trim(),
      command_template: template.trim(),
      description: description.trim() || undefined,
      enabled: command?.enabled ?? true,
    };

    if (command) {
      update.mutate(
        { name: command.name, command: payload },
        {
          onSuccess: () => {
            toast("Command updated", "success");
            onClose();
          },
          onError: () => toast("Update failed", "error"),
        },
      );
    } else {
      create.mutate(payload, {
        onSuccess: () => {
          toast("Command created", "success");
          onClose();
        },
        onError: () => toast("Create failed", "error"),
      });
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-sm">
            {command ? "Edit command" : "New command"}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label className="text-[11px] text-zinc-500 uppercase tracking-wider">
              Name
            </label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="market_data"
              className="mt-1 font-mono"
              disabled={!!command}
            />
          </div>

          <div>
            <label className="text-[11px] text-zinc-500 uppercase tracking-wider">
              Command template
            </label>
            <Textarea
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              placeholder='curl -s "https://api.example.com/ticker/{ticker}"'
              className="mt-1 font-mono text-xs min-h-[80px]"
            />
          </div>

          <div>
            <label className="text-[11px] text-zinc-500 uppercase tracking-wider">
              Description
            </label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Fetches real-time market data"
              className="mt-1"
            />
          </div>

          {/* Variable reference */}
          <div className="rounded border border-zinc-800 bg-zinc-950 p-2">
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">
              Variables
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
              {VARIABLES.map((v) => (
                <div key={v.name} className="flex items-center gap-1.5">
                  <code className="text-[10px] text-cyan-500/70 font-mono">
                    {v.name}
                  </code>
                  <span className="text-[10px] text-zinc-600">{v.desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={!name.trim() || !template.trim() || isPending}
          >
            {isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
            {command ? "Update" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
