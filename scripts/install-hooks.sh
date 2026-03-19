#!/usr/bin/env bash
# Install git hooks by creating symlinks from .git/hooks/ to scripts/hooks/

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/scripts/hooks"
GIT_HOOKS_DIR="$REPO_ROOT/.git/hooks"

for hook in "$HOOKS_DIR"/*; do
    hook_name="$(basename "$hook")"
    target="$GIT_HOOKS_DIR/$hook_name"

    if [ -L "$target" ] || [ -e "$target" ]; then
        # Back up non-symlink hooks
        if [ ! -L "$target" ] && [ -e "$target" ]; then
            mv "$target" "$target.bak"
            echo "Backed up existing $hook_name to $hook_name.bak"
        fi
        rm -f "$target"
    fi

    ln -s "$hook" "$target"
    echo "Installed $hook_name hook"
done
