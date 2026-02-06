import { cn } from "@/lib/utils";

interface ScoreBadgeProps {
  score: number | null;
  tier: string | null;
}

function tierLabel(tier: string | null): string {
  switch (tier) {
    case "high_signal":
      return "HIGH";
    case "market_relevant":
      return "MKT";
    case "news":
      return "NEWS";
    case "noise":
      return "NOISE";
    default:
      return "";
  }
}

export function ScoreBadge({ score, tier }: ScoreBadgeProps) {
  const s = score ?? 0;
  const label = tierLabel(tier);

  return (
    <span className="inline-flex items-baseline gap-1">
      <span
        className={cn(
          "font-mono text-sm font-semibold tabular-nums",
          s >= 9 && "text-green-400",
          s >= 7 && s < 9 && "text-green-500",
          s >= 5 && s < 7 && "text-yellow-500",
          s >= 3 && s < 5 && "text-zinc-300",
          s < 3 && "text-zinc-500",
        )}
      >
        {score !== null ? score.toFixed(1) : "—"}
      </span>
      {label && (
        <span
          className={cn(
            "text-[10px] font-medium uppercase tracking-wider",
            tier === "high_signal" && "text-green-400/60",
            tier === "market_relevant" && "text-cyan-400/60",
            tier === "news" && "text-violet-400/60",
            tier === "noise" && "text-zinc-300/70",
          )}
        >
          {label}
        </span>
      )}
    </span>
  );
}
