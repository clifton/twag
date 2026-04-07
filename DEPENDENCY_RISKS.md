# Dependency Risk Report

Generated: 2026-04-06

## Summary

| Category | Count | Severity |
|----------|-------|----------|
| Known CVEs (Python) | 0 | - |
| Known CVEs (JavaScript) | 3 packages / 5 advisories | High |
| Outdated Python packages | 8 of 13 | Low–Medium |
| Outdated JavaScript packages | 11 | Low–Medium |
| Loose version pins (Python) | 13 of 13 | Medium |

---

## 1. Known Vulnerabilities (CVEs)

### Python

**No known vulnerabilities found** via `pip-audit` (OSV database scan).

### JavaScript (dev-only)

All JS vulnerabilities are in **devDependencies** (build tooling), not shipped to production:

| Package | Severity | Advisory | Fix |
|---------|----------|----------|-----|
| **vite** <=6.4.1 | High | [GHSA-4w7w-66w2-5vf9](https://github.com/advisories/GHSA-4w7w-66w2-5vf9) — Path traversal in optimized deps `.map` handling | Update vite |
| **vite** <=6.4.1 | High | [GHSA-p9ff-h696-f583](https://github.com/advisories/GHSA-p9ff-h696-f583) — Arbitrary file read via WebSocket | Update vite |
| **rollup** 4.0.0–4.58.0 | High | [GHSA-mw96-cpmx-2vgc](https://github.com/advisories/GHSA-mw96-cpmx-2vgc) — Arbitrary file write via path traversal | Update rollup |
| **picomatch** 4.0.0–4.0.3 | High | [GHSA-3v7f-55p6-f55p](https://github.com/advisories/GHSA-3v7f-55p6-f55p) — Method injection in POSIX character classes | Update picomatch |
| **picomatch** 4.0.0–4.0.3 | High | [GHSA-c2c7-rcm5-vvqj](https://github.com/advisories/GHSA-c2c7-rcm5-vvqj) — ReDoS via extglob quantifiers | Update picomatch |

**Recommended action:** Run `npm audit fix` in `twag/web/frontend/` to resolve all five advisories.

---

## 2. Outdated Dependencies

### Python (runtime)

| Package | Installed | Latest | Gap |
|---------|-----------|--------|-----|
| anthropic | 0.77.0 | 0.89.0 | 12 minor versions behind |
| google-genai | 1.61.0 | 1.70.0 | 9 minor versions behind |
| fastapi | 0.128.0 | 0.135.3 | 7 minor versions behind |
| uvicorn | 0.40.0 | 0.44.0 | 4 minor versions behind |
| tabulate | 0.9.0 | 0.10.0 | 1 minor version behind |
| click | 8.3.1 | 8.3.2 | 1 patch behind |
| python-multipart | 0.0.22 | 0.0.24 | 2 patches behind |
| rich | 14.3.2 | 14.3.3 | 1 patch behind |

Up to date: httpx, python-dateutil, jinja2, pydantic, rich-click.

### JavaScript

| Package | Installed | Latest | Notes |
|---------|-----------|--------|-------|
| vite | 6.4.1 | 8.0.5 | Major version behind; security fixes |
| typescript | 5.9.3 | 6.0.2 | Major version behind |
| lucide-react | 0.469.0 | 1.7.0 | Major version behind |
| tailwind-merge | 2.6.1 | 3.5.0 | Major version behind |
| @tailwindcss/vite | 4.1.18 | 4.2.2 | Minor version behind |
| tailwindcss | 4.1.18 | 4.2.2 | Minor version behind |
| @tanstack/react-query | 5.90.20 | 5.96.2 | Minor version behind |
| @biomejs/biome | 2.3.14 | 2.4.10 | Minor version behind (dev) |
| @uiw/react-codemirror | 4.25.4 | 4.25.9 | Patch behind |
| react-router | 7.13.0 | 7.14.0 | Minor version behind |
| @types/react | 19.2.13 | 19.2.14 | Patch behind |

---

## 3. Version Pin Analysis (Python)

All 13 runtime dependencies use `>=` lower-bound pins with **no upper bound**:

```
"click>=8.1.0"
"anthropic>=0.40.0"
"google-genai>=1.0.0"
"httpx>=0.27.0"
"python-dateutil>=2.8.0"
"fastapi>=0.109.0"
"uvicorn[standard]>=0.27.0"
"jinja2>=3.1.0"
"python-multipart>=0.0.6"
"tabulate>=0.9.0"
"pydantic>=2.0"
"rich>=13.0"
"rich-click>=1.7"
```

**Risk:** Without upper bounds, a future major-version release of any dependency could be pulled in automatically and break the application. The `uv.lock` file mitigates this for reproducible installs, but fresh installs without the lock file are vulnerable.

**Recommendation:** For rapidly-evolving SDK packages (`anthropic`, `google-genai`), consider adding compatible-release pins (e.g., `anthropic>=0.77,<1.0`) to prevent accidental major-version upgrades.

---

## 4. Maintenance & Bus-Factor Risks

| Package | Risk | Notes |
|---------|------|-------|
| **tabulate** | Medium | Last release was Oct 2022 (0.9.0 → 0.10.0 gap is 2+ years). Low release cadence suggests limited active maintenance. |
| **python-multipart** | Low–Medium | Small, focused library. Historically slow release cadence but has had recent security-related patches. |
| **rich-click** | Low | Depends on both `rich` and `click` ecosystems. Maintained by a small team but actively developed. |
| **google-genai** | Low | Backed by Google; rapid iteration means frequent breaking changes — pin carefully. |
| **anthropic** | Low | Backed by Anthropic; same rapid iteration pattern. |

All other dependencies (`click`, `httpx`, `fastapi`, `uvicorn`, `jinja2`, `pydantic`, `rich`, `python-dateutil`) are well-maintained with large contributor bases and regular releases.

---

## 5. Recommended Actions

### Priority 1 — Security (do now)

1. **Run `npm audit fix`** in `twag/web/frontend/` to patch vite, rollup, and picomatch vulnerabilities.

### Priority 2 — Freshness (next sprint)

2. **Update `anthropic`** to latest (0.89.0) — SDK packages move fast and often include important fixes.
3. **Update `google-genai`** to latest (1.70.0) — same reasoning.
4. **Update `fastapi`** and `uvicorn` — multiple minor versions behind; may include performance and security improvements.
5. **Update `vite`** to at least 6.4.2+ (within v6 range) for security fixes; evaluate v7/v8 migration separately.

### Priority 3 — Hardening (planned)

6. **Add upper-bound pins** for `anthropic` and `google-genai` in `pyproject.toml` to prevent surprise breaking changes (e.g., `anthropic>=0.77,<1.0`).
7. **Evaluate `tabulate` alternatives** (e.g., `rich` already provides table formatting) given its slow maintenance cadence.
8. **Update remaining minor/patch-level** Python and JS dependencies as part of routine maintenance.
