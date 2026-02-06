import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function scoreColor(score: number | null): string {
  if (score === null) return "text-zinc-600";
  if (score >= 9) return "text-green-400";
  if (score >= 7) return "text-green-500";
  if (score >= 5) return "text-yellow-500";
  if (score >= 3) return "text-zinc-500";
  return "text-zinc-600";
}

export function scoreBg(score: number | null): string {
  if (score === null) return "bg-zinc-800/50";
  if (score >= 9) return "bg-green-500/15";
  if (score >= 7) return "bg-green-500/10";
  if (score >= 5) return "bg-yellow-500/10";
  if (score >= 3) return "bg-zinc-700/50";
  return "bg-zinc-800/30";
}

export function tierColor(tier: string | null): string {
  switch (tier) {
    case "high_signal":
      return "text-green-400";
    case "market_relevant":
      return "text-cyan-400";
    case "news":
      return "text-violet-400";
    case "noise":
      return "text-zinc-500";
    default:
      return "text-zinc-500";
  }
}

export function tierLabel(tier: string | null): string {
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
      return tier?.toUpperCase() ?? "";
  }
}
