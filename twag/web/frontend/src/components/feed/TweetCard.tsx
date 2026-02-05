import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScoreBadge } from "./ScoreBadge";
import { TweetContent } from "./TweetContent";
import { TweetMedia } from "./TweetMedia";
import { TweetActions } from "./TweetActions";
import { QuoteBlock } from "./QuoteBlock";
import type { AnalyzeResult, MediaItem, Tweet } from "@/api/types";
import { buildArticleVisuals } from "./articleVisuals";
import { timeAgo } from "@/lib/utils";

interface TweetCardProps {
  tweet: Tweet;
}

function compactLinkLabel(rawLabel: string, fallbackUrl: string): string {
  const label = (rawLabel || fallbackUrl || "").trim();
  if (label.length <= 64) return label;
  try {
    const parsed = new URL(fallbackUrl);
    const path = parsed.pathname && parsed.pathname !== "/" ? parsed.pathname : "";
    const shortPath = path.length > 22 ? `${path.slice(0, 22)}…` : path;
    return `${parsed.hostname}${shortPath}`;
  } catch {
    return `${label.slice(0, 61)}…`;
  }
}

function hasVisualSignal(items: MediaItem[] | null | undefined): boolean {
  if (!items?.length) return false;
  return items.some(
    (item) =>
      item.kind === "chart" ||
      item.kind === "table" ||
      item.kind === "document" ||
      Boolean(item.chart?.description || item.chart?.insight || item.table?.columns?.length),
  );
}

function mediaTextFallback(items: MediaItem[] | null | undefined): string | null {
  if (!items?.length) return null;
  for (const item of items) {
    const text =
      item.prose_summary ||
      item.short_description ||
      item.prose_text ||
      item.chart?.insight ||
      item.chart?.description ||
      item.table?.summary ||
      item.alt_text;
    if (text) {
      return text;
    }
  }
  return null;
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
  const [topArticleVisual, ...additionalArticleVisuals] = articleVisuals;
  const inlineQuoteEmbeds = tweet.inline_quote_embeds ?? [];
  const shouldShowMedia = tweet.has_media && !hasArticleSummary && hasVisualSignal(tweet.media_items);
  const mediaSummaryFallback =
    !hasArticleSummary && !shouldShowMedia
      ? (tweet.media_analysis ?? mediaTextFallback(tweet.media_items) ?? null)
      : null;
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
        <a
          href={tweetUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-auto inline-flex items-center gap-1 text-zinc-500 hover:text-zinc-200 transition-colors"
        >
          {hasArticleSummary && <span className="text-[10px] uppercase tracking-wide">Article</span>}
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>

      {/* Content */}
      <div className="mt-2">
        <TweetContent
          summary={digestBody}
          content={tweet.content}
          displayContent={tweet.display_content}
          showOriginalToggle={!hasArticleSummary}
          emphasizeSummary={hasArticleSummary}
        />
      </div>

      {/* Media */}
      {shouldShowMedia && (
        <div className="mt-3">
          <TweetMedia
            items={tweet.media_items}
            mediaAnalysis={tweet.media_analysis}
          />
        </div>
      )}

      {tweet.has_media && mediaSummaryFallback && (
        <p className="mt-2 text-xs text-zinc-300 leading-snug">{mediaSummaryFallback}</p>
      )}

      {/* Quote embed */}
      {tweet.quote_embed && (
        <div className="mt-2.5">
          <QuoteBlock quote={tweet.quote_embed} />
        </div>
      )}
      {inlineQuoteEmbeds.length > 0 && (
        <div className="mt-2 space-y-2">
          {inlineQuoteEmbeds.map((quote) => (
            <QuoteBlock key={`${tweet.id}-inline-${quote.id}`} quote={quote} />
          ))}
        </div>
      )}

      {/* Link summary */}
      {!hasArticleSummary && tweet.has_link && tweet.link_summary && (
        <p className="mt-2 text-xs text-zinc-300 leading-snug">
          {tweet.link_summary}
        </p>
      )}

      {tweet.external_links && tweet.external_links.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
          {tweet.external_links.slice(0, 3).map((link) => (
            <a
              key={`${tweet.id}-ext-${link.url}`}
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] text-cyan-300/85 hover:text-cyan-200 transition-colors underline decoration-cyan-700/40 underline-offset-2"
            >
              {compactLinkLabel(link.display_url || "", link.url)}
            </a>
          ))}
        </div>
      )}

      {/* X article summary */}
      {hasArticleSummary && (
        <section className="mt-3 space-y-3">
          <div
            className={`grid gap-3 ${
              tweet.article_primary_points.length > 0 && tweet.article_action_items.length > 0
                ? "lg:grid-cols-2 lg:gap-5"
                : "grid-cols-1"
            }`}
          >
            {tweet.article_primary_points.length > 0 && (
              <div className="space-y-1.5">
                <div className="text-[10px] uppercase tracking-wide text-zinc-400">Primary Points</div>
                <ul className="space-y-2">
                  {tweet.article_primary_points.slice(0, 4).map((point, idx) => (
                    <li key={`${tweet.id}-pp-${idx}`} className="flex gap-2.5">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-300/80" />
                      <div className="min-w-0">
                        <div className="text-[14px] text-zinc-100 leading-snug font-medium">{point.point}</div>
                        {point.reasoning ? (
                          <div className="mt-0.5 text-[13px] text-zinc-300 leading-snug">{point.reasoning}</div>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {tweet.article_action_items.length > 0 && (
              <div className="space-y-1.5">
                <div className="text-[10px] uppercase tracking-wide text-zinc-400">Actionable Items</div>
                <ul className="space-y-2">
                  {tweet.article_action_items.slice(0, 3).map((item, idx) => (
                    <li key={`${tweet.id}-ai-${idx}`} className="flex gap-2.5">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-300/80" />
                      <div className="min-w-0">
                        <div className="text-[14px] text-zinc-100 leading-snug font-medium">{item.action}</div>
                        {item.trigger ? (
                          <div className="mt-0.5 text-[13px] text-zinc-300 leading-snug">
                            <span className="text-[10px] uppercase tracking-wide text-zinc-500">Trigger</span>{" "}
                            {item.trigger}
                          </div>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {articleVisuals.length > 0 && (
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-wide text-zinc-400">Visuals</div>

              {topArticleVisual && (
                <a
                  key={`${tweet.id}-visual-top-${topArticleVisual.url}`}
                  href={topArticleVisual.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block"
                >
                  <img
                    src={topArticleVisual.url}
                    alt={topArticleVisual.keyTakeaway || `${topArticleVisual.kind} visual`}
                    className="block h-auto w-full rounded bg-zinc-950/60"
                    loading="lazy"
                  />
                  <div className="mt-1 text-[10px] text-zinc-500 uppercase tracking-wide">
                    {topArticleVisual.kind} (top)
                  </div>
                  {topArticleVisual.keyTakeaway && (
                    <div className="mt-0.5 text-[12px] text-zinc-300 leading-snug">
                      {topArticleVisual.keyTakeaway}
                    </div>
                  )}
                </a>
              )}

              {additionalArticleVisuals.length > 0 && (
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  {additionalArticleVisuals.map((visual, idx) => (
                    <a
                      key={`${tweet.id}-visual-${idx + 1}-${visual.url}`}
                      href={visual.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block"
                    >
                      <img
                        src={visual.url}
                        alt={visual.keyTakeaway || `${visual.kind} visual`}
                        className="block h-auto w-full rounded bg-zinc-950/60"
                        loading="lazy"
                      />
                      <div className="mt-1 text-[10px] text-zinc-500 uppercase tracking-wide">{visual.kind}</div>
                      {visual.keyTakeaway && (
                        <div className="mt-0.5 text-[12px] text-zinc-300 leading-snug">{visual.keyTakeaway}</div>
                      )}
                    </a>
                  ))}
                </div>
              )}
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

      {/* Bottom row: categories + tickers left, score + actions right */}
      <div className="mt-2.5 flex items-center justify-between gap-3">
        <div className="min-w-0 flex items-center gap-3">
          {tweet.categories.length > 0 && (
            <div className="flex items-center gap-1.5 whitespace-nowrap">
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
          {tweet.tickers.length > 0 && (
            <div className="min-w-0 flex-1">
              <div className="truncate whitespace-nowrap text-[10px] font-mono tracking-wide text-zinc-500/70 [mask-image:linear-gradient(to_right,black_75%,transparent)] [-webkit-mask-image:linear-gradient(to_right,black_75%,transparent)]">
                {tweet.tickers.map((t) => `$${t}`).join(" ")}
              </div>
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
