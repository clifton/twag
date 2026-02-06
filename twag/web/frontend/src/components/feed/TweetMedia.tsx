import { useState } from "react";
import type { MediaItem } from "@/api/types";

interface TweetMediaProps {
  items: MediaItem[] | null;
  mediaAnalysis: string | null;
}

function ChartMedia({ item }: { item: MediaItem }) {
  return (
    <div>
      {item.url && (
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block overflow-hidden rounded border border-zinc-800/50"
        >
          <img
            src={item.url}
            alt={item.alt_text ?? item.chart?.description ?? ""}
            className="w-full max-h-[400px] object-contain"
            loading="lazy"
          />
        </a>
      )}
      {item.chart?.description && (
        <p className="mt-1.5 text-xs text-zinc-300">{item.chart.description}</p>
      )}
      {item.chart?.insight && (
        <p className="mt-1 text-xs text-zinc-300 italic">
          {item.chart.insight}
        </p>
      )}
      {item.chart?.implication && (
        <p className="mt-1 text-xs text-amber-300/80">
          {item.chart.implication}
        </p>
      )}
    </div>
  );
}

function ProseMedia({ item }: { item: MediaItem }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded border border-zinc-700/70 bg-zinc-900/60 p-3">
      <p className="text-sm text-zinc-200 leading-relaxed">
        {item.prose_summary}
      </p>
      {item.prose_text && (
        <details
          open={open}
          onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
        >
          <summary className="mt-2 cursor-pointer text-xs text-zinc-300 hover:text-zinc-100 select-none">
            View extracted text
          </summary>
          <pre className="mt-2 max-h-60 overflow-y-auto whitespace-pre-wrap text-xs font-mono leading-relaxed text-zinc-300">
            {item.prose_text}
          </pre>
        </details>
      )}
    </div>
  );
}

function TableMedia({ item }: { item: MediaItem }) {
  const { table } = item;
  if (!table?.columns) return null;

  const rowCount = table.rows?.length ?? 0;
  const isLarge = rowCount > 10;

  const tableEl = (
    <div className="overflow-x-auto rounded border border-zinc-800 bg-zinc-900/50">
      <table className="w-full text-xs font-mono text-zinc-400">
        <thead>
          <tr className="border-b border-zinc-800">
            {table.columns.map((col, i) => (
              <th
                key={i}
                className="px-2 py-1.5 text-left text-zinc-300 font-medium whitespace-nowrap"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows?.map((row, ri) => (
            <tr key={ri} className="border-b border-zinc-800/50 last:border-0">
              {row.map((cell, ci) => (
                <td key={ci} className="px-2 py-1 whitespace-nowrap">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div>
      {item.url && (
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block overflow-hidden rounded border border-zinc-800/50 mb-2"
        >
          <img
            src={item.url}
            alt={item.alt_text ?? table.title ?? ""}
            className="w-full max-h-[400px] object-contain"
            loading="lazy"
          />
        </a>
      )}
      {table.summary && (
        <p className="mb-2 text-xs text-zinc-300">{table.summary}</p>
      )}
      {isLarge ? (
        <details>
          <summary className="cursor-pointer text-xs text-zinc-300 hover:text-zinc-100 select-none">
            Show table ({rowCount} rows)
          </summary>
          <div className="mt-2">{tableEl}</div>
        </details>
      ) : (
        tableEl
      )}
    </div>
  );
}

function DefaultMedia({ item }: { item: MediaItem }) {
  const caption = item.short_description || item.analysis;

  return (
    <div>
      {item.url && (
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block overflow-hidden rounded border border-zinc-800/50"
        >
          <img
            src={item.url}
            alt={item.alt_text ?? caption ?? ""}
            className="w-full max-h-[400px] object-contain"
            loading="lazy"
          />
        </a>
      )}
      {caption && (
        <p className="mt-1 text-xs text-zinc-300 italic">{caption}</p>
      )}
    </div>
  );
}

function renderMediaItem(item: MediaItem, index: number) {
  // 1. Chart
  if (item.kind === "chart" || item.chart?.description) {
    return <ChartMedia key={index} item={item} />;
  }

  // 2. Document / prose
  if (item.prose_summary) {
    return <ProseMedia key={index} item={item} />;
  }

  // 3. Table
  if (item.kind === "table" && item.table?.columns) {
    return <TableMedia key={index} item={item} />;
  }

  // 4. Default (photo / other)
  return <DefaultMedia key={index} item={item} />;
}

export function TweetMedia({ items, mediaAnalysis }: TweetMediaProps) {
  if (!items?.length && !mediaAnalysis) return null;

  return (
    <div className="space-y-2">
      {items?.slice(0, 4).map((item, i) => renderMediaItem(item, i))}

      {/* Fallback: overall media analysis if no structured items */}
      {mediaAnalysis && !items?.length && (
        <p className="text-xs text-zinc-300 leading-relaxed">{mediaAnalysis}</p>
      )}
    </div>
  );
}
