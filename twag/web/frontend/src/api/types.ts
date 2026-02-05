// API response types matching the FastAPI backend

export interface Tweet {
  id: string;
  author_handle: string;
  author_name: string | null;
  content: string | null;
  content_summary: string | null;
  summary: string | null;
  created_at: string | null;
  relevance_score: number | null;
  categories: string[];
  signal_tier: string | null;
  tickers: string[];
  bookmarked: boolean;
  has_quote: boolean;
  quote_tweet_id: string | null;
  has_media: boolean;
  media_analysis: string | null;
  media_items: MediaItem[] | null;
  has_link: boolean;
  link_summary: string | null;
  reactions: string | null;
  // Enriched fields (from enhanced API)
  quote_embed?: QuoteEmbed | null;
  reference_links?: ReferenceLink[];
  display_content?: string | null;
}

export interface QuoteEmbed {
  id: string;
  author_handle: string;
  author_name: string | null;
  content: string | null;
  created_at: string | null;
}

export interface ReferenceLink {
  id: string;
  url: string;
}

export interface MediaItem {
  type: string;
  url?: string;
  alt_text?: string;
  content?: string;
  analysis?: string;
  // Structured fields from vision analysis
  kind?: string;
  short_description?: string;
  prose_text?: string;
  prose_summary?: string;
  chart?: {
    type?: string;
    description?: string;
    insight?: string;
    implication?: string;
    tickers?: string[];
  };
  table?: {
    title?: string;
    description?: string;
    columns?: string[];
    rows?: string[][];
    summary?: string;
    tickers?: string[];
  };
}

export interface TweetsResponse {
  tweets: Tweet[];
  offset: number;
  limit: number;
  count: number;
  has_more: boolean;
}

export interface Category {
  name: string;
  count: number;
}

export interface CategoriesResponse {
  categories: Category[];
}

export interface Ticker {
  symbol: string;
  count: number;
}

export interface TickersResponse {
  tickers: Ticker[];
}

// Reactions
export interface Reaction {
  id: number;
  reaction_type: string;
  reason: string | null;
  target: string | null;
  created_at: string | null;
}

export interface ReactionsResponse {
  tweet_id: string;
  reactions: Reaction[];
}

export interface ReactionCreate {
  tweet_id: string;
  reaction_type: string;
  reason?: string;
  target?: string;
}

export interface ReactionsSummary {
  summary: Record<string, number>;
}

// Prompts
export interface Prompt {
  id: number;
  name: string;
  template: string;
  version: number;
  updated_at: string | null;
  updated_by: string | null;
}

export interface PromptsResponse {
  prompts: Prompt[];
}

export interface PromptHistory {
  name: string;
  history: PromptHistoryEntry[];
}

export interface PromptHistoryEntry {
  version: number;
  template: string;
  updated_at: string;
  updated_by: string;
}

export interface TuneResponse {
  prompt_name: string;
  current_version: number;
  analysis: string;
  suggested_prompt: string;
  reactions_analyzed: {
    high_importance: number;
    should_be_higher: number;
    less_important: number;
  };
  error?: string;
}

// Context Commands
export interface ContextCommand {
  id: number;
  name: string;
  command_template: string;
  description: string | null;
  enabled: boolean;
  created_at: string | null;
}

export interface ContextCommandsResponse {
  commands: ContextCommand[];
}

export interface ContextCommandCreate {
  name: string;
  command_template: string;
  description?: string;
  enabled?: boolean;
}

export interface CommandTestResult {
  command_name: string;
  command_template: string;
  final_command: string;
  variables_used: Record<string, string>;
  stdout: string;
  stderr: string;
  returncode: number;
  success: boolean;
  error?: string;
}

export interface AnalyzeResult {
  tweet_id: string;
  author: string;
  content: string;
  original_score: number;
  original_tier: string;
  context_commands_run: string[];
  context_data: Record<string, string>;
  analysis: string;
  error?: string;
}

// Filter state
export interface FeedFilters {
  since?: string;
  min_score?: number;
  signal_tier?: string;
  category?: string;
  ticker?: string;
  author?: string;
  bookmarked?: boolean;
  sort?: string;
}
