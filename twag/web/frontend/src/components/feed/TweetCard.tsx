import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScoreBadge } from "./ScoreBadge";
import { TweetContent } from "./TweetContent";
import { TweetMedia } from "./TweetMedia";
import { TweetActions } from "./TweetActions";
import { QuoteBlock } from "./QuoteBlock";
import type { AnalyzeResult, Tweet } from "@/api/types";
import { buildArticleVisuals } from "./articleVisuals";
import { timeAgo } from "@/lib/utils";

interface TweetCardProps {
  tweet: Tweet;
}

export function TweetCard({ tweet }: TweetCardProps) {
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null);

  const displayAuthor = tweet.display_author_handle || tweet.author_handle;
  const displayTweetId = tweet.display_tweet_id || tweet.id;
  const hasOriginalTweetTarget =
    tweet.is_retweet && displayTweetId.length > 0 && displayTweetId !== tweet.id;
  const linkAuthor = hasOriginalTweetTarget ? displayAuthor : tweet.author_handle;
  const linkTweetId = hasOriginalTweetTarget ? displayTweetId : tweet.id;
  const tweetUrl = `https://x.com/${linkAuthor}/status/${linkTweetId}`;
  const hasArticleSummary =
    tweet.is_x_article &&
    (Boolean(tweet.article_summary_short) ||
      tweet.article_primary_points.length > 0 ||
      tweet.article_action_items.length > 0);
  const articleVisuals = buildArticleVisuals(tweet.article_top_visual, tweet.media_items, 5);
  const digestBody =
    tweet.summary ??
    (tweet.is_x_article ? tweet.article_summary_short : null) ??
    tweet.content_summary;

  return (
    <article className="group border-b border-zinc-800/80 px-4 py-3 bg-zinc-950/40 hover:bg-zinc-900/20 transition-colors">
      {/* Line 1: @author · time · external link */}
      <div className="flex items-baseline gap-1.5 text-[11px] text-zinc-400">
        <a
          href={tweetUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="font-mono text-zinc-200 hover:text-cyan-300 transition-colors"
        >
          @{displayAuthor}
        </a>
        {tweet.is_retweet && tweet.retweeted_by_handle && (
          <span className="text-zinc-500">
            RT by @{tweet.retweeted_by_handle}
          </span>
        )}
        {tweet.created_at && (
          <>
            <span className="text-zinc-600">&middot;</span>
            <span className="font-mono">{timeAgo(tweet.created_at)}</span>
          </>
        )}
        {tweet.tickers.length > 0 && (
          <>
            <span className="text-zinc-600">&middot;</span>
            {tweet.tickers.map((t) => (
              <span key={t} className="font-mono text-cyan-300/80">
                ${t}
              </span>
            ))}
          </>
        )}
        <a
          href={tweetUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-auto text-zinc-500 hover:text-zinc-200 transition-colors"
        >
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>

      {/* Content */}
      <div className="mt-2">
        <TweetContent
          summary={digestBody}
          content={tweet.content}
          displayContent={tweet.display_content}
        />
      </div>

      {/* Media */}
      {tweet.has_media && !hasArticleSummary && (
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
      {!hasArticleSummary && tweet.has_link && tweet.link_summary && (
        <p className="mt-2 text-xs text-zinc-300 leading-snug">
          {tweet.link_summary}
        </p>
      )}

      {/* X article summary */}
      {hasArticleSummary && (
        <section className="mt-2 space-y-2 rounded border border-zinc-800/90 bg-zinc-900/25 p-2.5">
          {tweet.article_primary_points.length > 0 && (
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wide text-zinc-400">Primary Points</div>
              <ul className="space-y-1">
                {tweet.article_primary_points.slice(0, 4).map((point, idx) => (
                  <li key={`${tweet.id}-pp-${idx}`} className="text-[11px] text-zinc-200 leading-snug">
                    <span className="font-medium">{point.point}</span>
                    {point.reasoning ? <span className="text-zinc-300"> | {point.reasoning}</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {tweet.article_action_items.length > 0 && (
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wide text-zinc-400">Actionable Items</div>
              <ul className="space-y-1">
                {tweet.article_action_items.slice(0, 3).map((item, idx) => (
                  <li key={`${tweet.id}-ai-${idx}`} className="text-[11px] text-zinc-200 leading-snug">
                    <span className="font-medium">{item.action}</span>
                    {item.trigger ? <span className="text-zinc-300"> | trigger: {item.trigger}</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {articleVisuals.length > 0 && (
            <div className="space-y-1.5">
              <div className="text-[10px] uppercase tracking-wide text-zinc-400">Visuals</div>
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                {articleVisuals.map((visual, idx) => (
                  <a
                    key={`${tweet.id}-visual-${idx}-${visual.url}`}
                    href={visual.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded border border-zinc-800/80 bg-zinc-950/60 p-2 hover:border-cyan-700/60 transition-colors"
                  >
                    <img
                      src={visual.url}
                      alt={visual.keyTakeaway || `${visual.kind} visual`}
                      className="mb-1.5 h-28 w-full rounded object-cover"
                      loading="lazy"
                    />
                    <div className="text-[10px] text-zinc-400 uppercase tracking-wide">
                      {idx === 0 ? `${visual.kind} (top)` : visual.kind}
                    </div>
                    {visual.keyTakeaway && (
                      <div className="mt-0.5 text-[11px] text-zinc-200 leading-snug">
                        {visual.keyTakeaway}
                      </div>
                    )}
                  </a>
                ))}
              </div>
            </div>
          )}
        </section>
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
              className="text-[10px] text-zinc-400 hover:text-cyan-300 font-mono transition-colors"
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
                  className="text-[10px] font-medium uppercase tracking-wider text-zinc-400"
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
            authorHandle={displayAuthor}
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
              className="text-[10px] text-zinc-300 hover:text-zinc-100"
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
