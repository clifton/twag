#!/usr/bin/env bash
# Reproducibly regenerate the data behind DEPENDENCY_RISK.md.
#
# Outputs raw audit data to tmp/dependency_risk/ for manual review.
# This is read-only: it does not modify pyproject.toml, uv.lock, package.json,
# or package-lock.json, and does not install or upgrade anything.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/tmp/dependency_risk"
FRONTEND_DIR="${REPO_ROOT}/twag/web/frontend"

mkdir -p "${OUT_DIR}"

echo "==> Python: exporting locked requirements"
uv export --no-emit-project --quiet > "${OUT_DIR}/python_requirements.txt"

echo "==> Python: pip list --outdated"
uv pip list --outdated > "${OUT_DIR}/python_outdated.txt" || true

echo "==> Python: pip-audit (OSV + PyPI advisory DB)"
uv tool run pip-audit \
    --requirement "${OUT_DIR}/python_requirements.txt" \
    --format json > "${OUT_DIR}/python_pip_audit.json" \
    2> "${OUT_DIR}/python_pip_audit.stderr" || true

if [ -d "${FRONTEND_DIR}" ]; then
    echo "==> Frontend: npm audit"
    (cd "${FRONTEND_DIR}" && npm audit --json) > "${OUT_DIR}/frontend_npm_audit.json" || true

    echo "==> Frontend: npm outdated"
    (cd "${FRONTEND_DIR}" && npm outdated --json) > "${OUT_DIR}/frontend_npm_outdated.json" || true
else
    echo "==> Frontend directory not found, skipping npm audits"
fi

echo
echo "Audit data written to ${OUT_DIR}"
echo "Refresh DEPENDENCY_RISK.md by hand based on the JSON above."
