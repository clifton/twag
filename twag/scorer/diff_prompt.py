"""Prompt template for semantic diff explanation."""

DIFF_EXPLAIN_PROMPT = """\
You are a senior software engineer reviewing a code diff. Explain what these \
changes do semantically — focus on behavioral impact, new capabilities, removed \
functionality, bug fixes, and refactors. Do NOT recite individual line edits; \
instead describe the *intent* and *effect* of the changes in plain language.

Organize your explanation with short section headings where appropriate \
(e.g. "New feature", "Bug fix", "Refactor", "Breaking change"). Omit sections \
that don't apply. Be concise but thorough.

--- BEGIN DIFF ---
{diff}
--- END DIFF ---

Provide your explanation now."""
