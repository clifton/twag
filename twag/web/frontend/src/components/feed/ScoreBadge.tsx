import { cn } from "@/lib/utils";

interface ScoreBadgeProps {
  score: number | null;
  tier: string | null;
}

function tierLabel(tier: string | null): string {
  switch (tier) {
    case "high_signal": return "HIGH";
    case "market_relevant": return "MKT";
    case "news": return "NEWS";
    case "noise": return "NOISE";
    default: return "";
  }
}

export function ScoreBadge({ score, tier }: ScoreBadgeProps) {
  const s = score ?? 0;
  const label = tierLabel(tier);

  return (
    <div
      className={cn(
        "flex items-center gap-1.5 rounded px-2 py-0.5 font-mono tabular-nums",
        s >= 9 && "bg-green-500/15 text-green-400",
        s >= 7 && s < 9 && "bg-green-500/10 text-green-500",
        s >= 5 && s < 7 && "bg-yellow-500/10 text-yellow-500",
        s >= 3 && s < 5 && "bg-zinc-700/50 text-zinc-400",
        s < 3 && "bg-zinc-800/30 text-zinc-600",
      )}
    >
      <span className="text-sm font-semibold leading-none">
        {score !== null ? score.toFixed(1) : "—"}
      </span>
      {label && (
        <span
          className={cn(
            "text-[10px] font-medium leading-none uppercase tracking-wider",
            tier === "high_signal" && "text-green-400/70",
            tier === "market_relevant" && "text-cyan-400/70",
            tier === "news" && "text-violet-400/70",
            tier === "noise" && "text-zinc-500/70",
          )}
        >
          {label}
        </span>
      )}
    </div>
  );
}
