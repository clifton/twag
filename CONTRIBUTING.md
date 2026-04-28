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
5. Commit with a descriptive message (see [Commit Messages](#commit-messages))
6. Push and open a PR

## Commit Messages

twag follows the [Conventional Commits](https://www.conventionalcommits.org/)
specification. The subject line must match:

```
<type>(<scope>)?: <subject>
```

### Allowed types

| Type       | Use for                                              |
|------------|------------------------------------------------------|
| `feat`     | A new user-facing feature                            |
| `fix`      | A bug fix                                            |
| `docs`     | Documentation-only changes                           |
| `style`    | Formatting / whitespace (no behavior change)         |
| `refactor` | Code change that is neither a feature nor a fix      |
| `perf`     | Performance improvement                              |
| `test`     | Adding or fixing tests                               |
| `chore`    | Tooling, dependencies, repo maintenance              |
| `build`    | Build system or packaging changes                    |
| `ci`       | CI configuration                                     |
| `revert`   | Revert a previous commit                             |

### Subject rules

- Optional `<scope>` is a short noun describing the area touched
  (e.g. `fetcher`, `scorer`, `web`, `db`).
- Imperative mood: "add", not "added" / "adds".
- Keep the entire subject line at or below **72 characters**.
- No trailing period.

### Body and trailers

- Separate body from subject with a blank line; wrap at ~72 chars.
- Use the body to explain *why*, not *what*.
- Optional trailers go at the end, one per line:
  - `Co-Authored-By: Name <email@example.com>`
  - `Refs: #123`
  - `BREAKING CHANGE: <description>`

### Example

```
feat(scorer): add cached prompt for long-tail accounts

The default prompt was being recomputed for low-volume accounts, which
blew the rate limit during overnight batches. Cache by author handle.

Refs: #456
```

### Enabling the template and hook

The repo ships a commit message template and a `commit-msg` hook that
validates the subject line. Both are opt-in:

```bash
# Use the template when running `git commit` without -m
git config commit.template .gitmessage

# Run the validator on every commit
git config core.hooksPath scripts/hooks
```

Alternatively, run `scripts/setup-hooks.sh` to symlink hooks into
`.git/hooks/`. Merge and `fixup!` / `squash!` commits are skipped by the
validator.

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
