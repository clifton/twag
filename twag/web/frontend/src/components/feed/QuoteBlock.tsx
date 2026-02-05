import type { QuoteEmbed } from "@/api/types";
import { timeAgo } from "@/lib/utils";

interface QuoteBlockProps {
  quote: QuoteEmbed;
}

export function QuoteBlock({ quote }: QuoteBlockProps) {
  return (
    <div className="border-l-2 border-zinc-700 pl-2.5 py-1">
      <div className="flex items-center gap-1.5 text-[11px] text-zinc-500">
        <span className="font-mono">@{quote.author_handle}</span>
        {quote.created_at && (
          <>
            <span className="text-zinc-700">&middot;</span>
            <span>{timeAgo(quote.created_at)}</span>
          </>
        )}
      </div>
      {quote.content && (
        <p className="mt-0.5 text-xs text-zinc-400 leading-snug line-clamp-3">
          {quote.content}
        </p>
      )}
    </div>
  );
}
