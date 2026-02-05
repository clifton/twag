import { useState } from "react";
import { ChevronDown, ChevronUp, Image, BarChart3, FileText } from "lucide-react";
import type { MediaItem } from "@/api/types";

interface TweetMediaProps {
  items: MediaItem[] | null;
  mediaAnalysis: string | null;
}

export function TweetMedia({ items, mediaAnalysis }: TweetMediaProps) {
  const [expanded, setExpanded] = useState(false);

  if (!items?.length && !mediaAnalysis) return null;

  const images = items?.filter((m) => m.type === "image" || m.type === "photo") ?? [];
  const charts = items?.filter((m) => m.type === "chart") ?? [];
  const tables = items?.filter((m) => m.type === "table") ?? [];

  return (
    <div className="space-y-1">
      {/* Thumbnails row */}
      {images.length > 0 && (
        <div className="flex gap-1">
          {images.slice(0, 4).map((img, i) =>
            img.url ? (
              <a
                key={i}
                href={img.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block h-12 w-12 overflow-hidden rounded border border-zinc-800 hover:border-zinc-600 transition-colors"
              >
                <img
                  src={img.url}
                  alt={img.alt_text ?? ""}
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              </a>
            ) : (
              <div
                key={i}
                className="flex h-12 w-12 items-center justify-center rounded border border-zinc-800 bg-zinc-900"
              >
                <Image className="h-4 w-4 text-zinc-600" />
              </div>
            ),
          )}
        </div>
      )}

      {/* Indicator chips */}
      <div className="flex items-center gap-2">
        {charts.length > 0 && (
          <span className="flex items-center gap-1 text-[11px] text-cyan-500/70">
            <BarChart3 className="h-3 w-3" /> {charts.length} chart{charts.length > 1 ? "s" : ""}
          </span>
        )}
        {tables.length > 0 && (
          <span className="flex items-center gap-1 text-[11px] text-violet-400/70">
            <FileText className="h-3 w-3" /> table
          </span>
        )}
        {mediaAnalysis && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-0.5 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            Analysis
          </button>
        )}
      </div>

      {/* Expanded analysis */}
      {expanded && mediaAnalysis && (
        <div className="rounded border border-zinc-800 bg-zinc-900/50 p-2 text-xs text-zinc-400 leading-relaxed">
          {mediaAnalysis}
        </div>
      )}

      {/* Tables inline */}
      {tables.map((t, i) =>
        t.content ? (
          <div
            key={i}
            className="overflow-x-auto rounded border border-zinc-800 bg-zinc-900/50 p-2 text-xs font-mono text-zinc-400 leading-relaxed"
          >
            <pre className="whitespace-pre">{t.content}</pre>
          </div>
        ) : null,
      )}
    </div>
  );
}
