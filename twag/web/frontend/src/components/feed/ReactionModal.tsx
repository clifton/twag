import { useState, useEffect, useRef } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ReactionModalProps {
  type: string;
  onConfirm: (reason?: string) => void;
  onClose: () => void;
}

const typeLabels: Record<string, string> = {
  ">>": "Mark as top tier",
  ">": "Mark as underrated",
  "<": "Mark as overrated",
};

export function ReactionModal({ type, onConfirm, onClose }: ReactionModalProps) {
  const [reason, setReason] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // Focus textarea after dialog animation
    const timer = setTimeout(() => textareaRef.current?.focus(), 100);
    return () => clearTimeout(timer);
  }, []);

  const handleSubmit = () => {
    onConfirm(reason.trim() || undefined);
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="font-mono text-sm">
            {typeLabels[type] ?? type}
          </DialogTitle>
        </DialogHeader>
        <Textarea
          ref={textareaRef}
          placeholder="Why? (optional)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="min-h-[80px] text-sm"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              handleSubmit();
            }
          }}
        />
        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSubmit}>
            Submit
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
