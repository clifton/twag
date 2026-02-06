import type { ArticleTopVisual, MediaItem } from "@/api/types";

export interface DataVisual {
  url: string;
  kind: string;
  isTop: boolean;
  keyTakeaway: string;
  whyImportant: string;
}

const DATA_KINDS = new Set(["chart", "table", "document", "screenshot"]);
const TEXTUAL_DATA_RE =
  /\b(chart|graph|table|capex|revenue|margin|growth|yoy|qoq|forecast|projection|run[-\s]?rate|backlog|roi|ebitda|eps)\b/;
const NUMERIC_DATA_RE =
  /(\$|\b\d+(\.\d+)?%|\b\d+(\.\d+)?\s?(b|m|bn|mn|trillion|billion|million)\b)/;
const NOISE_RE = /\b(meme|reaction image|shitpost|joke|selfie|portrait)\b/;

function buildTextBlob(item: MediaItem): string {
  return [
    item.short_description,
    item.prose_summary,
    item.prose_text,
    item.alt_text,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function looksDataLikeText(text: string): boolean {
  if (!text) return false;
  if (NOISE_RE.test(text)) return false;
  return TEXTUAL_DATA_RE.test(text) || NUMERIC_DATA_RE.test(text);
}

function inferKind(item: MediaItem): string {
  const rawKind = (item.kind ?? "").toLowerCase();
  if (DATA_KINDS.has(rawKind)) return rawKind;
  if (item.chart?.description || item.chart?.insight || item.chart?.implication)
    return "chart";
  if (item.table?.columns?.length || item.table?.summary) return "table";
  if (looksDataLikeText(buildTextBlob(item))) return "chart";
  return rawKind;
}

function extractTakeaway(item: MediaItem, kind: string): string {
  if (kind === "chart") {
    return (
      item.chart?.insight ??
      item.chart?.implication ??
      item.chart?.description ??
      ""
    );
  }
  if (kind === "table") {
    return item.table?.summary ?? item.table?.description ?? "";
  }
  if (kind === "document" || kind === "screenshot") {
    return item.prose_summary ?? item.short_description ?? "";
  }
  return item.short_description ?? "";
}

function isRelevantVisual(item: MediaItem, kind: string): boolean {
  if (DATA_KINDS.has(kind)) return true;
  return looksDataLikeText(buildTextBlob(item));
}

export function buildArticleVisuals(
  topVisual: ArticleTopVisual | null,
  mediaItems: MediaItem[] | null,
  maxItems = 5,
): DataVisual[] {
  if (maxItems <= 0) return [];

  const visuals: DataVisual[] = [];
  const seen = new Set<string>();

  if (topVisual?.url) {
    const topKind = (topVisual.kind || "visual").toLowerCase();
    const topText =
      `${topVisual.key_takeaway || ""} ${topVisual.why_important || ""}`.toLowerCase();
    if (DATA_KINDS.has(topKind) || looksDataLikeText(topText)) {
      visuals.push({
        url: topVisual.url,
        kind: DATA_KINDS.has(topKind) ? topKind : "chart",
        isTop: true,
        keyTakeaway: topVisual.key_takeaway || "",
        whyImportant: topVisual.why_important || "",
      });
      seen.add(topVisual.url);
    }
  }

  const extras: Array<{ priority: number; visual: DataVisual }> = [];
  for (const item of mediaItems ?? []) {
    if (!item?.url || seen.has(item.url)) continue;
    const kind = inferKind(item);
    if (!isRelevantVisual(item, kind)) continue;
    const normalizedKind = DATA_KINDS.has(kind) ? kind : "chart";
    extras.push({
      priority:
        { chart: 0, table: 1, screenshot: 2, document: 3 }[normalizedKind] ?? 9,
      visual: {
        url: item.url,
        kind: normalizedKind,
        isTop: false,
        keyTakeaway: extractTakeaway(item, kind),
        whyImportant: "",
      },
    });
    seen.add(item.url);
  }

  extras.sort((a, b) => a.priority - b.priority);
  for (const extra of extras) {
    if (visuals.length >= maxItems) break;
    visuals.push(extra.visual);
  }

  return visuals;
}
