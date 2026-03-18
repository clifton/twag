#!/bin/sh
# Set up git hooks by symlinking from scripts/hooks/ into .git/hooks/
set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/scripts/hooks"

for hook in "$HOOKS_DIR"/*; do
    hook_name="$(basename "$hook")"
    target="$REPO_ROOT/.git/hooks/$hook_name"
    ln -sf "$hook" "$target"
    echo "Linked $hook_name -> $hook"
done

echo "Git hooks installed."
