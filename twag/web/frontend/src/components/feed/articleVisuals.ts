import type { ArticleTopVisual, MediaItem } from "@/api/types";

export interface DataVisual {
  url: string;
  kind: string;
  isTop: boolean;
  keyTakeaway: string;
  whyImportant: string;
}

const DATA_KINDS = new Set(["chart", "table", "document", "screenshot"]);

function inferKind(item: MediaItem): string {
  const rawKind = (item.kind ?? "").toLowerCase();
  if (DATA_KINDS.has(rawKind)) return rawKind;
  if (item.chart?.description || item.chart?.insight || item.chart?.implication) return "chart";
  if (item.table?.columns?.length || item.table?.summary) return "table";
  return rawKind;
}

function extractTakeaway(item: MediaItem, kind: string): string {
  if (kind === "chart") {
    return item.chart?.insight ?? item.chart?.implication ?? item.chart?.description ?? "";
  }
  if (kind === "table") {
    return item.table?.summary ?? item.table?.description ?? "";
  }
  if (kind === "document" || kind === "screenshot") {
    return item.prose_summary ?? item.short_description ?? "";
  }
  return item.short_description ?? "";
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
    visuals.push({
      url: topVisual.url,
      kind: (topVisual.kind || "visual").toLowerCase(),
      isTop: true,
      keyTakeaway: topVisual.key_takeaway || "",
      whyImportant: topVisual.why_important || "",
    });
    seen.add(topVisual.url);
  }

  const extras: Array<{ priority: number; visual: DataVisual }> = [];
  for (const item of mediaItems ?? []) {
    if (!item?.url || seen.has(item.url)) continue;
    const kind = inferKind(item);
    if (!DATA_KINDS.has(kind)) continue;
    extras.push({
      priority: { chart: 0, table: 1, screenshot: 2, document: 3 }[kind] ?? 9,
      visual: {
        url: item.url,
        kind,
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
