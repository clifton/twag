import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCategories, useTickers } from "@/hooks/use-categories";
import type { FeedFilters } from "@/api/types";

interface FilterBarProps {
  filters: FeedFilters;
  setFilter: (key: keyof FeedFilters, value: string | number | boolean | undefined) => void;
  clearFilters: () => void;
  activeFilterCount: number;
}

export function FilterBar({
  filters,
  setFilter,
  clearFilters,
  activeFilterCount,
}: FilterBarProps) {
  const { data: catData } = useCategories();
  const { data: tickerData } = useTickers();

  return (
    <div className="flex items-center gap-2 border-b border-zinc-800 bg-zinc-950/80 px-4 py-1.5 backdrop-blur-sm overflow-x-auto">
      {/* Time range */}
      <Select
        value={filters.since ?? ""}
        onValueChange={(v) => setFilter("since", v || undefined)}
      >
        <SelectTrigger className="w-[90px]">
          <SelectValue placeholder="Time" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="today">Today</SelectItem>
          <SelectItem value="24h">24h</SelectItem>
          <SelectItem value="7d">7d</SelectItem>
          <SelectItem value="30d">30d</SelectItem>
        </SelectContent>
      </Select>

      {/* Min score */}
      <Select
        value={filters.min_score?.toString() ?? ""}
        onValueChange={(v) => setFilter("min_score", v ? Number(v) : undefined)}
      >
        <SelectTrigger className="w-[90px]">
          <SelectValue placeholder="Score" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="3">3+</SelectItem>
          <SelectItem value="5">5+</SelectItem>
          <SelectItem value="7">7+</SelectItem>
          <SelectItem value="8">8+</SelectItem>
          <SelectItem value="9">9+</SelectItem>
        </SelectContent>
      </Select>

      {/* Signal tier */}
      <Select
        value={filters.signal_tier ?? ""}
        onValueChange={(v) => setFilter("signal_tier", v || undefined)}
      >
        <SelectTrigger className="w-[100px]">
          <SelectValue placeholder="Tier" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="high_signal">High Signal</SelectItem>
          <SelectItem value="market_relevant">Market</SelectItem>
          <SelectItem value="news">News</SelectItem>
          <SelectItem value="noise">Noise</SelectItem>
        </SelectContent>
      </Select>

      {/* Category */}
      <Select
        value={filters.category ?? ""}
        onValueChange={(v) => setFilter("category", v || undefined)}
      >
        <SelectTrigger className="w-[110px]">
          <SelectValue placeholder="Category" />
        </SelectTrigger>
        <SelectContent>
          {catData?.categories.map((c) => (
            <SelectItem key={c.name} value={c.name}>
              {c.name} ({c.count})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Ticker */}
      <Select
        value={filters.ticker ?? ""}
        onValueChange={(v) => setFilter("ticker", v || undefined)}
      >
        <SelectTrigger className="w-[90px]">
          <SelectValue placeholder="$TICK" />
        </SelectTrigger>
        <SelectContent>
          {tickerData?.tickers.slice(0, 30).map((t) => (
            <SelectItem key={t.symbol} value={t.symbol}>
              ${t.symbol} ({t.count})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Author search */}
      <Input
        placeholder="@author"
        value={filters.author ?? ""}
        onChange={(e) => setFilter("author", e.target.value || undefined)}
        className="h-7 w-[100px] text-xs font-mono"
      />

      {/* Bookmarked toggle */}
      <Button
        variant={filters.bookmarked ? "secondary" : "ghost"}
        size="sm"
        onClick={() => setFilter("bookmarked", !filters.bookmarked || undefined)}
        className="text-xs"
      >
        {filters.bookmarked ? "★" : "☆"}
      </Button>

      {/* Sort */}
      <Select
        value={filters.sort ?? "relevance"}
        onValueChange={(v) => setFilter("sort", v === "relevance" ? undefined : v)}
      >
        <SelectTrigger className="w-[100px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="relevance">Relevance</SelectItem>
          <SelectItem value="latest">Latest</SelectItem>
        </SelectContent>
      </Select>

      {/* Clear filters */}
      {activeFilterCount > 0 && (
        <Button variant="ghost" size="sm" onClick={clearFilters} className="text-xs text-zinc-500">
          <X className="h-3 w-3" />
          Clear ({activeFilterCount})
        </Button>
      )}
    </div>
  );
}
