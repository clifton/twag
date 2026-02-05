import { useState } from "react";

interface TweetContentProps {
  summary: string | null;
  content: string | null;
  displayContent?: string | null;
}

export function TweetContent({ summary, content, displayContent }: TweetContentProps) {
  const [expanded, setExpanded] = useState(false);
  const text = displayContent ?? content;
  const hasFull = text && text !== summary && text.length > 0;

  return (
    <div className="space-y-1">
      {summary && (
        <p className="text-sm text-zinc-200 leading-relaxed">{summary}</p>
      )}
      {!summary && text && !expanded && (
        <p className="text-sm text-zinc-300 leading-relaxed line-clamp-4">{text}</p>
      )}
      {expanded && text && (
        <p className="text-sm text-zinc-400 leading-relaxed whitespace-pre-wrap">{text}</p>
      )}
      {hasFull && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          {expanded ? "Hide" : "Show original"}
        </button>
      )}
    </div>
  );
}
