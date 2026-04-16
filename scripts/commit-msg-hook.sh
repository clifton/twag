#!/usr/bin/env bash
# commit-msg hook validating Conventional Commits format.
#
# Install locally:
#   ln -s ../../scripts/commit-msg-hook.sh .git/hooks/commit-msg
#   chmod +x scripts/commit-msg-hook.sh
#
# The hook reads the commit message file ($1) and rejects non-conforming
# subjects. It skips merges, reverts, fixups, squashes, and empty messages.

set -eu

msg_file="${1:-}"
if [ -z "$msg_file" ] || [ ! -f "$msg_file" ]; then
    exit 0
fi

# First non-comment, non-empty line is the subject.
subject="$(grep -v '^#' "$msg_file" | sed '/^[[:space:]]*$/d' | head -n 1 || true)"

if [ -z "$subject" ]; then
    exit 0
fi

# Skip exempt prefixes: merge commits, reverts, fixup!/squash!, GitHub web commits.
case "$subject" in
    "Merge "*|"Revert "*|"fixup! "*|"squash! "*|"amend! "*)
        exit 0
        ;;
esac

# Allowed types: feat, fix, docs, chore, refactor, perf, test, build, ci, style, revert.
# Grammar: type(scope)?!?: subject  —  subject non-empty, whole line under 72 chars.
pattern='^(feat|fix|docs|chore|refactor|perf|test|build|ci|style|revert)(\([a-z0-9._/-]+\))?!?: [^ ].*$'

if ! printf '%s' "$subject" | grep -Eq "$pattern"; then
    cat >&2 <<EOF
ERROR: commit subject does not follow Conventional Commits.

  Got:      $subject

  Expected: <type>(<optional scope>): <imperative subject>
            Types: feat, fix, docs, chore, refactor, perf,
                   test, build, ci, style, revert

  Examples:
    feat(cli): add narratives list command
    fix: expand t.co links before storing
    docs: standardize commit message format

See CONTRIBUTING.md for the full spec.
EOF
    exit 1
fi

if [ "${#subject}" -gt 72 ]; then
    echo "ERROR: commit subject is ${#subject} chars; keep it under 72." >&2
    echo "  Subject: $subject" >&2
    exit 1
fi

exit 0
