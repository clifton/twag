import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScoreBadge } from "./ScoreBadge";
import { TweetContent } from "./TweetContent";
import { TweetMedia } from "./TweetMedia";
import { TweetActions } from "./TweetActions";
import { QuoteBlock } from "./QuoteBlock";
import type { AnalyzeResult, Tweet } from "@/api/types";
import { timeAgo } from "@/lib/utils";

interface TweetCardProps {
  tweet: Tweet;
}

export function TweetCard({ tweet }: TweetCardProps) {
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null);

  const tweetUrl = `https://x.com/${tweet.author_handle}/status/${tweet.id}`;

  return (
    <article className="group border-b border-zinc-800/40 px-4 py-3">
      {/* Line 1: @author · time · external link */}
      <div className="flex items-baseline gap-1.5 text-[11px] text-zinc-500">
        <a
          href={tweetUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="font-mono text-zinc-400 hover:text-cyan-400 transition-colors"
        >
          @{tweet.author_handle}
        </a>
        {tweet.created_at && (
          <>
            <span className="text-zinc-700">&middot;</span>
            <span className="font-mono">{timeAgo(tweet.created_at)}</span>
          </>
        )}
        {tweet.tickers.length > 0 && (
          <>
            <span className="text-zinc-700">&middot;</span>
            {tweet.tickers.map((t) => (
              <span key={t} className="font-mono text-cyan-500/70">
                ${t}
              </span>
            ))}
          </>
        )}
        <a
          href={tweetUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-auto text-zinc-700 hover:text-zinc-400 transition-colors"
        >
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>

      {/* Content */}
      <div className="mt-2">
        <TweetContent
          summary={tweet.summary ?? tweet.content_summary}
          content={tweet.content}
          displayContent={tweet.display_content}
        />
      </div>

      {/* Media */}
      {tweet.has_media && (
        <div className="mt-3">
          <TweetMedia
            items={tweet.media_items}
            mediaAnalysis={tweet.media_analysis}
          />
        </div>
      )}

      {/* Quote embed */}
      {tweet.quote_embed && (
        <div className="mt-2.5">
          <QuoteBlock quote={tweet.quote_embed} />
        </div>
      )}

      {/* Link summary */}
      {tweet.has_link && tweet.link_summary && (
        <p className="mt-2 text-xs text-zinc-500 leading-snug">
          {tweet.link_summary}
        </p>
      )}

      {/* Reference links */}
      {tweet.reference_links && tweet.reference_links.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {tweet.reference_links.map((link) => (
            <a
              key={link.id}
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] text-zinc-600 hover:text-cyan-400 font-mono transition-colors"
            >
              ref:{link.id.slice(-6)}
            </a>
          ))}
        </div>
      )}

      {/* Bottom row: categories left, score + actions right */}
      <div className="mt-2.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {tweet.categories.length > 0 && (
            <div className="flex items-center gap-1.5">
              {tweet.categories.map((c) => (
                <span
                  key={c}
                  className="text-[10px] font-medium uppercase tracking-wider text-zinc-600"
                >
                  {c.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <TweetActions
            tweetId={tweet.id}
            authorHandle={tweet.author_handle}
            onAnalyze={setAnalysis}
          />
          <ScoreBadge score={tweet.relevance_score} tier={tweet.signal_tier} />
        </div>
      </div>

      {/* Analysis result */}
      {analysis && (
        <div className="mt-2 rounded border border-cyan-900/50 bg-cyan-950/20 p-3">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-medium text-cyan-400">Deep Analysis</span>
            <button
              onClick={() => setAnalysis(null)}
              className="text-[10px] text-zinc-500 hover:text-zinc-300"
            >
              dismiss
            </button>
          </div>
          {analysis.context_commands_run.length > 0 && (
            <div className="mb-1.5 flex flex-wrap gap-1">
              {analysis.context_commands_run.map((cmd) => (
                <Badge key={cmd} variant="outline" className="text-[10px]">
                  {cmd}
                </Badge>
              ))}
            </div>
          )}
          <div className="text-xs text-zinc-300 leading-relaxed whitespace-pre-wrap">
            {analysis.analysis}
          </div>
        </div>
      )}
    </article>
  );
}
