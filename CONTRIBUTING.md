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
5. Commit with a descriptive message
6. Push and open a PR

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
