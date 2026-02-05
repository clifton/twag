import { useState } from "react";

const SUMMARY_MIN_LENGTH = 280;

interface TweetContentProps {
  summary: string | null;
  content: string | null;
  displayContent?: string | null;
}

export function shouldShowSummary(summary: string | null, renderedText: string | null): boolean {
  if (!summary) return false;
  if (!renderedText) return true;
  return renderedText.length >= SUMMARY_MIN_LENGTH;
}

export function TweetContent({ summary, content, displayContent }: TweetContentProps) {
  const [expanded, setExpanded] = useState(false);
  const text = displayContent ?? content;
  const summaryVisible = shouldShowSummary(summary, text);
  const hasFull = summaryVisible && text && text !== summary && text.length > 0;

  return (
    <div className="space-y-1">
      {summaryVisible && summary && (
        <p className="text-sm text-zinc-100 leading-relaxed">{summary}</p>
      )}
      {!summaryVisible && text && !expanded && (
        <p className="text-sm text-zinc-200 leading-relaxed line-clamp-4">{text}</p>
      )}
      {expanded && text && (
        <p className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">{text}</p>
      )}
      {hasFull && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          {expanded ? "Hide" : "Show original"}
        </button>
      )}
    </div>
  );
}
