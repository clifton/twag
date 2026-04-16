# Contributing to twag

Thanks for your interest in contributing!

## Development Setup

```bash
# Clone the repo
git clone https://github.com/clifton/twag.git
cd twag

# Install with dev dependencies
pip install -e ".[dev]"

# Install frontend dependencies
cd twag/web/frontend
npm install
```

## Running Tests

```bash
# Python tests
pytest

# With coverage
pytest --cov=twag

# Lint check
ruff check .

# Format check
ruff format --check .
```

## Code Style

- Python: Ruff for linting and formatting
- TypeScript/React: Prettier (via npm)
- Line length: 120 characters

Run before committing:

```bash
ruff format .
ruff check --fix .
```

## Making Changes

1. Fork the repo
2. Create a feature branch: `git checkout -b my-feature`
3. Make your changes
4. Run tests and linting
5. Commit with a descriptive message (see [Commit Message Format](#commit-message-format))
6. Push and open a PR

## Commit Message Format

This project follows [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

### Subject line

```
<type>(<optional scope>): <imperative subject>
```

- **type** (required, lowercase): one of `feat`, `fix`, `docs`, `chore`, `refactor`, `perf`, `test`, `build`, `ci`, `style`, `revert`
- **scope** (optional): short noun identifying the affected area (e.g. `cli`, `db`, `fetcher`, `web`)
- **subject** (required): imperative mood, no trailing period, keep under 72 characters total

Examples:

```
feat(cli): add narratives list command
fix: expand t.co links before storing
docs: standardize commit message format
refactor(db): extract connection helper
```

### Allowed types

| Type | Use for |
|------|---------|
| `feat` | New user-facing feature |
| `fix` | Bug fix |
| `docs` | Documentation-only changes |
| `chore` | Tooling, deps, version bumps, misc maintenance |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | Performance improvement |
| `test` | Adding or fixing tests |
| `build` | Build system or external dependency changes |
| `ci` | CI configuration changes |
| `style` | Formatting, whitespace (no behavior change) |
| `revert` | Reverting a previous commit |

### Body and footers

- Optional body after a blank line explaining *why* (not *what*).
- Optional footers/trailers like `Co-Authored-By:`, `Refs: #123`, `BREAKING CHANGE: ...`.
- Merge commits and GitHub-generated commits are exempt.

### Optional local hook

A lightweight commit-msg hook ships in `scripts/commit-msg-hook.sh`. Install it locally to get format validation on every commit:

```bash
ln -s ../../scripts/commit-msg-hook.sh .git/hooks/commit-msg
chmod +x scripts/commit-msg-hook.sh
```

The hook rejects non-conforming subjects, but skips merges, reverts, and fixups. CI does not enforce this yet.

## Documentation

If you change CLI behavior:
- Update `README.md` (user-facing docs)
- Update `SKILL.md` (OpenClaw quick reference)
- Update `CLAUDE.md` if architecture changes

## Reporting Issues

Open an issue at https://github.com/clifton/twag/issues with:
- What you expected
- What happened
- Steps to reproduce
- `twag doctor` output (redact API keys)

## Questions?

Open a discussion or issue — happy to help!
