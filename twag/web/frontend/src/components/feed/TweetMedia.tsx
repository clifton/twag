import type { MediaItem } from "@/api/types";

interface TweetMediaProps {
  items: MediaItem[] | null;
  mediaAnalysis: string | null;
}

export function TweetMedia({ items, mediaAnalysis }: TweetMediaProps) {
  if (!items?.length && !mediaAnalysis) return null;

  const visuals =
    items?.filter(
      (m) => m.type === "image" || m.type === "photo" || m.type === "chart",
    ) ?? [];
  const tables = items?.filter((m) => m.type === "table") ?? [];

  return (
    <div className="space-y-2">
      {/* Full-width images / charts */}
      {visuals.slice(0, 4).map((img, i) =>
        img.url ? (
          <div key={i}>
            <a
              href={img.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block overflow-hidden rounded border border-zinc-800/50"
            >
              <img
                src={img.url}
                alt={img.alt_text ?? ""}
                className="w-full max-h-[400px] object-contain"
                loading="lazy"
              />
            </a>
            {img.analysis && (
              <p className="mt-1 text-xs text-zinc-500 italic">{img.analysis}</p>
            )}
          </div>
        ) : null,
      )}

      {/* Media analysis (shown by default) */}
      {mediaAnalysis && (
        <p className="text-xs text-zinc-500 leading-relaxed">{mediaAnalysis}</p>
      )}

      {/* Tables */}
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
