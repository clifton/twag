# Roadmap

Planned work themes and priorities for the twag project.

## Themes

### pipeline-reliability
Harden the fetch → process → digest pipeline: retries, rate-limit handling,
error notifications, locking, and parallel execution safety.

### scoring-quality
Improve LLM scoring accuracy, prompt tuning, model upgrades, and enrichment
(article summaries, visual selection, narrative extraction).

### web-feed
Expand the FastAPI web feed: tweet display, context routes, reactions,
inline quote embeds, and the React frontend.

### cli-ux
Rich CLI output, search, account management commands, config surface, and
doctor/init flows.

### ops-automation
Cron scheduling, Telegram digest delivery, OpenClaw skill integration,
CI/CD (auto version bump, PyPI publish), and developer tooling.

### data-integrity
Database schema maintenance, FTS rebuilds, dump/restore, migration scripts,
link normalization, and dependency ingestion hardening.

### docs
Keep README, SKILL.md, CLAUDE.md, INSTALL.md, and TELEGRAM_DIGEST_FORMAT.md
in sync with code changes.

### lint-quality
Ruff rule adoption, type checking (ty), formatting enforcement, and
test coverage improvements.
