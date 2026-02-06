import { Fragment, useState } from "react";

const SUMMARY_MIN_LENGTH = 500;
const URL_RE = /(https?:\/\/[^\s]+)/g;

interface TweetContentProps {
  summary: string | null;
  content: string | null;
  displayContent?: string | null;
  showOriginalToggle?: boolean;
  emphasizeSummary?: boolean;
}

export function shouldShowSummary(
  summary: string | null,
  renderedText: string | null,
): boolean {
  if (!summary) return false;
  if (!renderedText) return true;
  return renderedText.length >= SUMMARY_MIN_LENGTH;
}

export function TweetContent({
  summary,
  content,
  displayContent,
  showOriginalToggle = true,
  emphasizeSummary = false,
}: TweetContentProps) {
  const [expanded, setExpanded] = useState(false);
  const text = displayContent ?? content;
  const summaryVisible = shouldShowSummary(summary, text);
  const hasFull =
    showOriginalToggle &&
    summaryVisible &&
    text &&
    text !== summary &&
    text.length > 0;

  const renderText = (value: string, className: string) => {
    const lines = value.split("\n");
    return (
      <p className={className}>
        {lines.map((line, lineIdx) => {
          const chunks = line.split(URL_RE);
          return (
            <Fragment key={`line-${lineIdx}`}>
              {chunks.map((chunk, chunkIdx) => {
                if (!chunk) return null;
                if (
                  chunk.startsWith("http://") ||
                  chunk.startsWith("https://")
                ) {
                  return (
                    <a
                      key={`chunk-${lineIdx}-${chunkIdx}`}
                      href={chunk}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-cyan-300/90 hover:text-cyan-200 underline decoration-cyan-700/50 underline-offset-2"
                    >
                      {chunk}
                    </a>
                  );
                }
                return (
                  <Fragment key={`chunk-${lineIdx}-${chunkIdx}`}>
                    {chunk}
                  </Fragment>
                );
              })}
              {lineIdx < lines.length - 1 ? <br /> : null}
            </Fragment>
          );
        })}
      </p>
    );
  };

  return (
    <div className="space-y-1">
      {summaryVisible &&
        summary &&
        renderText(
          summary,
          emphasizeSummary
            ? "text-[15px] text-zinc-50 leading-relaxed whitespace-pre-wrap font-medium"
            : "text-sm text-zinc-100 leading-relaxed whitespace-pre-wrap",
        )}
      {!summaryVisible &&
        text &&
        !expanded &&
        renderText(
          text,
          "text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap",
        )}
      {expanded &&
        text &&
        renderText(
          text,
          "text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap",
        )}
      {hasFull && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          {expanded ? "Hide" : "Show original"}
        </button>
      )}
    </div>
  );
}
