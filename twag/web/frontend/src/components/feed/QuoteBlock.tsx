import type { QuoteEmbed } from "@/api/types";
import { cn } from "@/lib/utils";
import { timeAgo } from "@/lib/utils";

interface QuoteBlockProps {
  quote: QuoteEmbed;
}

interface QuoteNodeProps {
  quote: QuoteEmbed;
  depth: number;
}

function QuoteNode({ quote, depth }: QuoteNodeProps) {
  return (
    <div
      className={cn(
        "rounded-md border border-zinc-700/70 bg-zinc-900/55 p-2.5",
        depth > 0 && "mt-2",
      )}
    >
      <div className="flex items-center gap-1.5 text-[11px] text-zinc-300">
        <span className="font-mono text-zinc-200">@{quote.author_handle}</span>
        {quote.created_at && (
          <>
            <span className="text-zinc-600">&middot;</span>
            <span>{timeAgo(quote.created_at)}</span>
          </>
        )}
      </div>
      {quote.content && (
        <p className="mt-1 text-xs text-zinc-200/95 leading-snug line-clamp-6">
          {quote.content}
        </p>
      )}
      {quote.quote_embed && depth < 2 && (
        <div className="mt-2 border-l border-zinc-700/70 pl-2.5">
          <QuoteNode quote={quote.quote_embed} depth={depth + 1} />
        </div>
      )}
    </div>
  );
}

export function QuoteBlock({ quote }: QuoteBlockProps) {
  return <QuoteNode quote={quote} depth={0} />;
}
