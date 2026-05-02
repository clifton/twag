# Dependency Risk Report

Generated: 2026-05-01

This report inventories direct and notable transitive dependencies for the
twag Python project and the React frontend, classifies each by risk level,
and lists recommended follow-ups. It is **read-only**: no version pins,
lockfiles, or source files were changed by this scan. Re-run the scan with
`scripts/dependency_risk_scan.sh` to refresh the underlying data.

## Summary

| Ecosystem | Direct deps | Vulnerable | Outdated | Notes |
| --- | --- | --- | --- | --- |
| Python (runtime) | 13 | 0 direct, 5 transitive | 8 minor, 1 major | `starlette` is 1 major behind via `fastapi` |
| Python (dev) | 4 | 1 (`pytest`) | 3 | `ty` is pre-1.0 (0.0.x), expected churn |
| Frontend (deps) | 16 | 0 direct | 4 | `lucide-react` major bump available |
| Frontend (devDeps) | 8 | 1 (`vite`) | 4 | `vite` 2 majors behind, ReDoS chain via transitive `picomatch`/`rollup`/`postcss` |

**Vulnerability counts** (advisory IDs in the per-package tables below):

- Python: **9 advisories across 7 packages** (1 high — `cryptography` SECT subgroup; rest medium/low).
- Frontend: **4 advisories across 4 packages** (3 high, 1 moderate); only `vite` is a direct dep, the others are transitive under it.

No package in either ecosystem is known to be archived or deprecated upstream.

---

## Python — Runtime dependencies

Source: `pyproject.toml` `[project.dependencies]` and resolved `uv.lock`.
Vulnerabilities from `pip-audit` (PyPI advisory DB + OSV).

| Package | Pin | Resolved | Latest | Status | Advisory / Note |
| --- | --- | --- | --- | --- | --- |
| `click` | `>=8.1.0` | 8.3.1 | 8.3.3 | OK | patch behind |
| `anthropic` | `>=0.40.0` | 0.77.0 | 0.97.0 | outdated | 20 minor releases behind; SDK changes regularly |
| `google-genai` | `>=1.0.0` | 1.61.0 | 1.74.0 | outdated | 13 minor releases behind |
| `httpx` | `>=0.27.0` | 0.28.1 | 0.28.1 | OK | current |
| `python-dateutil` | `>=2.8.0` | 2.9.0.post0 | 2.9.0.post0 | OK | current |
| `fastapi` | `>=0.109.0` | 0.128.0 | 0.136.1 | outdated | 8 minor releases behind |
| `uvicorn[standard]` | `>=0.27.0` | 0.40.0 | 0.46.0 | outdated | 6 minor releases behind |
| `jinja2` | `>=3.1.0` | 3.1.6 | 3.1.6 | OK | current |
| `python-multipart` | `>=0.0.6` | 0.0.22 | 0.0.27 | **vulnerable** | CVE-2026-40347 (multipart preamble/epilogue DoS), fix in 0.0.26 |
| `tabulate` | `>=0.9.0` | 0.9.0 | 0.10.0 | outdated | one minor behind |
| `pydantic` | `>=2.0` | 2.12.5 | 2.13.3 | OK | one minor behind |
| `rich` | `>=13.0` | 14.3.2 | 15.0.0 | outdated | one major behind |
| `rich-click` | `>=1.7` | 1.9.7 | 1.9.7 | OK | current |

### Notable transitive vulnerabilities (Python)

| Package | Resolved | Fix versions | Advisory | Severity |
| --- | --- | --- | --- | --- |
| `cryptography` (via `google-auth`) | 46.0.4 | 46.0.5 / 46.0.6 / 46.0.7 | CVE-2026-26007 (SECT subgroup), CVE-2026-34073 (Name Constraints), CVE-2026-39892 (non-contiguous buffer overflow) | high |
| `requests` (via `pip-audit`/google) | 2.32.5 | 2.33.0 | CVE-2026-25645 (`extract_zipped_paths` temp races) — only matters if app calls it directly | low |
| `pyasn1` (via `google-auth`) | 0.6.2 | 0.6.3 | CVE-2026-30922 (uncontrolled recursion DoS in BER decoder) | medium |
| `pygments` (via `rich`) | 2.19.2 | 2.20.0 | CVE-2026-4539 (`AdlLexer` ReDoS) | low |
| `python-dotenv` (via `google-genai`) | 1.2.1 | 1.2.2 | CVE-2026-28684 (symlink-following on cross-device rename) | medium |
| `starlette` (via `fastapi`) | 0.50.0 | 1.0.0 | one major behind, no current advisory but fastapi pins lag | medium |

### Other transitive observations

- `urllib3` 2.6.3 / `idna` 3.11 / `certifi` 2026.1.4: all behind latest but **no open advisories**.
- `cffi` 2.0.0, `markupsafe` 3.0.3, `pydantic-core` 2.41.5: clean.

---

## Python — Dev dependencies

Source: `pyproject.toml` `[dependency-groups.dev]`.

| Package | Pin | Resolved | Latest | Status | Advisory / Note |
| --- | --- | --- | --- | --- | --- |
| `pytest` | `>=9.0.2` | 9.0.2 | 9.0.3 | **vulnerable** | CVE-2025-71176 (`/tmp/pytest-of-{user}` predictable dir, local DoS / privilege risk), fix in 9.0.3 |
| `pytest-cov` | `>=6.0` | 7.0.0 | 7.1.0 | outdated | one minor behind |
| `ruff` | `>=0.9` | 0.15.0 | 0.15.12 | outdated | dev tool, low risk |
| `ty` | `*` | 0.0.15 | 0.0.34 | unmaintained-shape | pre-1.0, by design rapidly changing; **bump regularly** |

`ty` is a young tool — the gap is large but expected. Pinning a more specific
version would just trade churn for stale type results.

---

## Frontend — Runtime dependencies

Source: `twag/web/frontend/package.json` and resolved `package-lock.json`.
Vulnerabilities from `npm audit`.

| Package | Pin | Current | Latest | Status | Note |
| --- | --- | --- | --- | --- | --- |
| `@codemirror/lang-markdown` | `^6.3.0` | 6.x | 6.x | OK | current within range |
| `@codemirror/theme-one-dark` | `^6.1.2` | 6.x | 6.x | OK | current |
| `@radix-ui/react-*` | `^1.1.x` / `^2.1.x` | matches | matches | OK | Radix is actively maintained |
| `@tanstack/react-query` | `^5.62.0` | 5.90.20 | 5.100.7 | outdated | 10 minor releases behind, same major |
| `@uiw/react-codemirror` | `^4.23.0` | 4.25.4 | 4.25.9 | OK | patch behind |
| `class-variance-authority` | `^0.7.1` | 0.7.x | 0.7.x | OK | |
| `clsx` | `^2.1.1` | 2.x | 2.x | OK | |
| `codemirror` | `^6.0.1` | 6.x | 6.x | OK | |
| `lucide-react` | `^0.469.0` | 0.469.0 | 1.14.0 | outdated (major) | crossed 1.0; review breaking changes |
| `react` | `^19.0.0` | 19.2.4 | 19.2.5 | OK | one patch behind |
| `react-dom` | `^19.0.0` | 19.2.4 | 19.2.5 | OK | one patch behind |
| `react-router` | `^7.1.0` | 7.13.0 | 7.14.2 | OK | one minor behind |
| `tailwind-merge` | `^2.6.0` | 2.6.1 | 3.5.0 | outdated (major) | 1 major behind |

### Frontend devDependencies

| Package | Pin | Current | Latest | Status | Note |
| --- | --- | --- | --- | --- | --- |
| `@biomejs/biome` | `^2.3.14` | 2.3.14 | 2.4.14 | outdated | one minor behind |
| `@tailwindcss/vite` | `^4.0.0` | 4.1.18 | 4.2.4 | OK | one minor behind |
| `@types/react` | `^19.0.0` | 19.2.13 | 19.2.14 | OK | |
| `@types/react-dom` | `^19.0.0` | matches | matches | OK | |
| `@vitejs/plugin-react` | `^4.3.0` | 4.7.0 | 6.0.1 | outdated (major) | 2 majors behind |
| `tailwindcss` | `^4.0.0` | 4.1.18 | 4.2.4 | OK | one minor behind |
| `typescript` | `^5.7.0` | 5.9.3 | 6.0.3 | outdated (major) | 1 major behind |
| `vite` | `^6.0.0` | 6.4.1 | 8.0.10 | **vulnerable** | 2 majors behind; CVE chain below |

### Frontend vulnerabilities (from `npm audit`)

| Package | Severity | Direct? | Advisory | Reachable from |
| --- | --- | --- | --- | --- |
| `vite` | high | yes | GHSA-4w7w-66w2-5vf9 (path traversal in optimized deps `.map`), GHSA-p9ff-h696-f583 (arbitrary file read via dev-server WS) | `vite` (devDep) |
| `rollup` | high | no | GHSA-mw96-cpmx-2vgc (arbitrary file write via path traversal, < 4.59.0) | `vite` |
| `postcss` | moderate | no | GHSA-qx2v-qp2m-jg93 (XSS via unescaped `</style>`) | `vite` → `tailwindcss` |
| `picomatch` | high | no | GHSA-c2c7-rcm5-vvqj (ReDoS via extglob), GHSA-3v7f-55p6-f55p (POSIX class injection) | `vite` chain |

All four resolve by upgrading `vite` (and re-running `npm install`).

---

## Recommended actions

**P0 — security**

1. Bump `cryptography` to ≥ 46.0.7 (covers all three CVEs). Pulled in via `google-auth`; bumping `google-auth` or letting `uv lock --upgrade-package cryptography` resolve is sufficient.
2. Upgrade `vite` to its latest 8.x (or at minimum a `vite` release that pins `rollup` ≥ 4.59 and `postcss` ≥ 8.5.10). This is a frontend-only change — verify `npm run build` still passes.
3. Bump `python-multipart` to ≥ 0.0.26 and `python-dotenv` to ≥ 1.2.2; both are reachable via the FastAPI / google-genai stacks.
4. Bump `pyasn1` to ≥ 0.6.3 and `pytest` to ≥ 9.0.3.

**P1 — drift**

5. Refresh `anthropic` (0.77 → 0.97), `google-genai` (1.61 → 1.74), `fastapi` (0.128 → 0.136). Each has 8–20 minors of drift; verify model/SDK call sites and FastAPI/Starlette deprecations.
6. Cross the `starlette` 0.x → 1.0 boundary when `fastapi` does — currently fastapi still pins 0.x.

**P2 — frontend majors**

7. `lucide-react` 0.469 → 1.x: icon imports may have renamed; touch is wide but mechanical.
8. `tailwind-merge` 2 → 3, `@vitejs/plugin-react` 4 → 6, `typescript` 5 → 6: each warrants its own PR with `npm run build` + a quick visual check.

**P3 — hygiene**

9. Bump `pygments` (2.19 → 2.20) and `requests` (2.32.5 → 2.33.x) to clear low-severity CVEs even though neither attack path is reached today.
10. Periodically refresh `ty` — pre-1.0, expect frequent renames in lint/type rules.

None of the above require source code edits in this PR; they are tracked here so a maintainer can prioritize the bumps.

---

## Methodology

- **Python inventory:** parsed `pyproject.toml` for direct pins, `uv.lock` for resolved versions; cross-checked with `uv pip list` and `uv pip list --outdated`.
- **Python advisories:** `uv tool run pip-audit --requirement <exported requirements>` against the OSV / PyPI advisory database.
- **Frontend inventory:** parsed `twag/web/frontend/package.json` for direct pins, `npm outdated --json` for current vs latest.
- **Frontend advisories:** `npm audit --json` against the GitHub Advisory Database.
- **Classification rule:**
  - **vulnerable** — at least one open CVE / GHSA with an available fix version.
  - **outdated (major)** — ≥ 1 major version behind latest.
  - **outdated** — ≥ 1 minor version behind latest stable, no advisory.
  - **OK** — at most a patch behind, no advisory.
  - **unmaintained-shape** — pre-1.0 tool with rapid version churn (here only `ty`); flagged separately to avoid noise.
- Scan was performed on 2026-05-01 against the lockfiles on branch `nightshift/dependency-risk-v2`.

To regenerate the underlying audit data:

```bash
./scripts/dependency_risk_scan.sh
```

Output lands in `tmp/dependency_risk/` and is gitignored.
