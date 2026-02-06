"""Database schema definitions for twag."""

SCHEMA = """
-- Tweets: Core storage with deduplication
CREATE TABLE IF NOT EXISTS tweets (
    id TEXT PRIMARY KEY,
    author_handle TEXT NOT NULL,
    author_name TEXT,
    content TEXT NOT NULL,
    created_at TIMESTAMP,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT,

    -- LLM processing results
    processed_at TIMESTAMP,
    relevance_score REAL,
    category TEXT,
    summary TEXT,
    content_summary TEXT,  -- Summarized content for long tweets
    signal_tier TEXT,
    tickers TEXT,
    analysis_json TEXT,

    -- Expansion tracking
    has_quote INTEGER DEFAULT 0,
    quote_tweet_id TEXT,
    in_reply_to_tweet_id TEXT,
    conversation_id TEXT,
    has_media INTEGER DEFAULT 0,
    media_analysis TEXT,
    media_items TEXT,
    has_link INTEGER DEFAULT 0,
    links_json TEXT,
    link_summary TEXT,
    is_x_article INTEGER DEFAULT 0,
    article_title TEXT,
    article_preview TEXT,
    article_text TEXT,
    article_summary_short TEXT,
    article_primary_points_json TEXT,
    article_action_items_json TEXT,
    article_top_visual_json TEXT,
    article_processed_at TIMESTAMP,
    links_expanded_at TIMESTAMP,
    quote_reprocessed_at TIMESTAMP,
    is_retweet INTEGER DEFAULT 0,
    retweeted_by_handle TEXT,
    retweeted_by_name TEXT,
    original_tweet_id TEXT,
    original_author_handle TEXT,
    original_author_name TEXT,
    original_content TEXT,

    -- Output tracking
    included_in_digest TEXT,

    -- Bookmarks
    bookmarked INTEGER DEFAULT 0,
    bookmarked_at TIMESTAMP,

    FOREIGN KEY (quote_tweet_id) REFERENCES tweets(id)
);

-- Accounts: Tracking with boost/decay
CREATE TABLE IF NOT EXISTS accounts (
    handle TEXT PRIMARY KEY,
    display_name TEXT,
    tier INTEGER DEFAULT 2,
    weight REAL DEFAULT 50.0,
    category TEXT,

    -- Stats
    tweets_seen INTEGER DEFAULT 0,
    tweets_kept INTEGER DEFAULT 0,
    avg_relevance_score REAL,
    last_high_signal_at TIMESTAMP,
    last_fetched_at TIMESTAMP,

    -- Management
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    auto_promoted INTEGER DEFAULT 0,
    muted INTEGER DEFAULT 0
);

-- Narratives: Emerging theme tracking
CREATE TABLE IF NOT EXISTS narratives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_mentioned_at TIMESTAMP,
    mention_count INTEGER DEFAULT 1,
    sentiment TEXT,
    related_tickers TEXT,
    active INTEGER DEFAULT 1
);

-- Tweet-Narrative junction
CREATE TABLE IF NOT EXISTS tweet_narratives (
    tweet_id TEXT,
    narrative_id INTEGER,
    PRIMARY KEY (tweet_id, narrative_id),
    FOREIGN KEY (tweet_id) REFERENCES tweets(id),
    FOREIGN KEY (narrative_id) REFERENCES narratives(id)
);

-- Fetch history: Rate limit tracking
CREATE TABLE IF NOT EXISTS fetch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tweets_fetched INTEGER,
    new_tweets INTEGER,
    query_params TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tweets_created ON tweets(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tweets_score ON tweets(relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_tweets_unprocessed ON tweets(processed_at) WHERE processed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_accounts_tier ON accounts(tier, weight DESC);

-- Feed query and filter indexes
CREATE INDEX IF NOT EXISTS idx_tweets_processed_score ON tweets(processed_at, relevance_score DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tweets_processed_created ON tweets(processed_at, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tweets_author ON tweets(author_handle);
CREATE INDEX IF NOT EXISTS idx_tweets_signal_tier ON tweets(signal_tier);
CREATE INDEX IF NOT EXISTS idx_tweets_bookmarked ON tweets(bookmarked) WHERE bookmarked = 1;
CREATE INDEX IF NOT EXISTS idx_tweets_quote ON tweets(quote_tweet_id) WHERE quote_tweet_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fetch_log_endpoint ON fetch_log(endpoint, executed_at DESC);

-- User reactions for feedback loop
CREATE TABLE IF NOT EXISTS reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    reaction_type TEXT NOT NULL,  -- '>>', '>', '<', 'x_author', 'x_topic'
    reason TEXT,                   -- optional: why this should be rated differently
    target TEXT,                   -- author handle or category for X reactions
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tweet_id) REFERENCES tweets(id)
);

-- Editable prompts (extracted from scorer.py)
CREATE TABLE IF NOT EXISTS prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,     -- 'triage', 'batch_triage', 'enrichment', etc.
    template TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT                -- 'user' or 'llm'
);

-- Prompt history for rollback
CREATE TABLE IF NOT EXISTS prompt_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_name TEXT NOT NULL,
    template TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- CLI commands for context enrichment
CREATE TABLE IF NOT EXISTS context_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,      -- 'market_snapshot', 'ticker_price', etc.
    command_template TEXT NOT NULL, -- 'python scripts/market_at.py --date {tweet_date}'
    description TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Additional indexes for new tables
CREATE INDEX IF NOT EXISTS idx_reactions_tweet ON reactions(tweet_id);
CREATE INDEX IF NOT EXISTS idx_reactions_type ON reactions(reaction_type);
CREATE INDEX IF NOT EXISTS idx_prompt_history_name ON prompt_history(prompt_name, version DESC);
"""

# FTS5 schema for full-text search
FTS_SCHEMA = """
-- Full-text search virtual table
CREATE VIRTUAL TABLE IF NOT EXISTS tweets_fts USING fts5(
    content,
    summary,
    author_handle,
    tickers,
    content=tweets,
    content_rowid=rowid
);

-- Trigger to keep FTS in sync on INSERT
CREATE TRIGGER IF NOT EXISTS tweets_ai AFTER INSERT ON tweets BEGIN
    INSERT INTO tweets_fts(rowid, content, summary, author_handle, tickers)
    VALUES (NEW.rowid, NEW.content, NEW.summary, NEW.author_handle, NEW.tickers);
END;

-- Trigger to keep FTS in sync on DELETE
CREATE TRIGGER IF NOT EXISTS tweets_ad AFTER DELETE ON tweets BEGIN
    INSERT INTO tweets_fts(tweets_fts, rowid, content, summary, author_handle, tickers)
    VALUES ('delete', OLD.rowid, OLD.content, OLD.summary, OLD.author_handle, OLD.tickers);
END;

-- Trigger to keep FTS in sync on UPDATE
CREATE TRIGGER IF NOT EXISTS tweets_au AFTER UPDATE ON tweets BEGIN
    INSERT INTO tweets_fts(tweets_fts, rowid, content, summary, author_handle, tickers)
    VALUES ('delete', OLD.rowid, OLD.content, OLD.summary, OLD.author_handle, OLD.tickers);
    INSERT INTO tweets_fts(rowid, content, summary, author_handle, tickers)
    VALUES (NEW.rowid, NEW.content, NEW.summary, NEW.author_handle, NEW.tickers);
END;
"""
