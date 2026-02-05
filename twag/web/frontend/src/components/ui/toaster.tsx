import { useCallback, useEffect, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface Toast {
  id: number;
  message: string;
  type: "success" | "error" | "info";
}

let toastId = 0;
const listeners = new Set<(toast: Toast) => void>();

export function toast(message: string, type: Toast["type"] = "info") {
  const t: Toast = { id: ++toastId, message, type };
  listeners.forEach((fn) => fn(t));
}

export function Toaster() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((t: Toast) => {
    setToasts((prev) => [...prev, t]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== t.id));
    }, 4000);
  }, []);

  useEffect(() => {
    listeners.add(addToast);
    return () => { listeners.delete(addToast); };
  }, [addToast]);

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            "flex items-center gap-2 rounded border px-3 py-2 text-sm shadow-lg animate-in slide-in-from-bottom-2",
            t.type === "success" && "border-green-800 bg-green-950 text-green-300",
            t.type === "error" && "border-red-800 bg-red-950 text-red-300",
            t.type === "info" && "border-zinc-700 bg-zinc-900 text-zinc-300",
          )}
        >
          <span className="flex-1">{t.message}</span>
          <button
            onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
            className="text-zinc-500 hover:text-zinc-300"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      ))}
    </div>
  );
}
