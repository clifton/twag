import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

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
        <p className="text-sm text-zinc-300 leading-snug">{summary}</p>
      )}
      {!summary && text && !expanded && (
        <p className="text-sm text-zinc-400 leading-snug line-clamp-2">{text}</p>
      )}
      {expanded && text && (
        <p className="text-sm text-zinc-400 leading-snug whitespace-pre-wrap">{text}</p>
      )}
      {hasFull && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-0.5 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          {expanded ? (
            <>
              <ChevronUp className="h-3 w-3" /> Hide
            </>
          ) : (
            <>
              <ChevronDown className="h-3 w-3" /> Full content
            </>
          )}
        </button>
      )}
    </div>
  );
}
