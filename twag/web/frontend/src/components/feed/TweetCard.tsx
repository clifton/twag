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
    <div className="border-b border-zinc-800/50 px-4 py-2.5 hover:bg-zinc-900/30 transition-colors">
      {/* Row 1: Score + metadata */}
      <div className="flex items-start gap-2.5">
        <ScoreBadge score={tweet.relevance_score} tier={tweet.signal_tier} />

        <div className="flex-1 min-w-0">
          {/* Metadata line */}
          <div className="flex items-center gap-1.5 text-[11px] text-zinc-500 flex-wrap">
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
            {tweet.categories.length > 0 && (
              <>
                <span className="text-zinc-700">&middot;</span>
                {tweet.categories.map((c) => (
                  <Badge
                    key={c}
                    variant={
                      (c === "high_signal" || c === "market_relevant" || c === "news" || c === "noise")
                        ? c as "high_signal" | "market_relevant" | "news" | "noise"
                        : "secondary"
                    }
                    className="text-[10px] py-0"
                  >
                    {c}
                  </Badge>
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
          <div className="mt-1">
            <TweetContent
              summary={tweet.summary ?? tweet.content_summary}
              content={tweet.content}
              displayContent={tweet.display_content}
            />
          </div>

          {/* Link summary */}
          {tweet.has_link && tweet.link_summary && (
            <div className="mt-1 rounded border border-zinc-800/50 bg-zinc-900/30 px-2 py-1 text-xs text-zinc-500 leading-snug">
              {tweet.link_summary}
            </div>
          )}

          {/* Quote embed */}
          {tweet.quote_embed && (
            <div className="mt-1.5">
              <QuoteBlock quote={tweet.quote_embed} />
            </div>
          )}

          {/* Media */}
          {tweet.has_media && (
            <div className="mt-1.5">
              <TweetMedia
                items={tweet.media_items}
                mediaAnalysis={tweet.media_analysis}
              />
            </div>
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

          {/* Actions row */}
          <div className="mt-1 flex items-center justify-between">
            <TweetActions
              tweetId={tweet.id}
              authorHandle={tweet.author_handle}
              onAnalyze={setAnalysis}
            />
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
        </div>
      </div>
    </div>
  );
}
