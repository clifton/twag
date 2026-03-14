# Dependency Audit Report

**Date:** 2026-03-13
**Tools used:** pip-audit, npm audit, npm outdated

---

## Summary

| Category | Count |
|----------|-------|
| Python vulnerabilities found | 1 (fixed) |
| Node.js vulnerabilities found | 1 (fixed) |
| Python packages outdated | 0 (direct deps up to date) |
| Node.js packages outdated | 11 (non-security, no action taken) |

## Python Vulnerabilities

### CVE-2026-26007 — cryptography (FIXED)

- **Package:** cryptography
- **Severity:** High
- **Affected version:** 46.0.4
- **Fixed version:** 46.0.5
- **Description:** `public_key_from_numbers`, `EllipticCurvePublicNumbers.public_key()`, `load_der_public_key()` and `load_pem_public_key()` do not verify that the point belongs to the expected prime-order subgroup of the curve. This allows an attacker to provide a public key point from a small-order subgroup, leaking information about the private key via ECDH, or enabling signature forgery via ECDSA. Only SECT curves are impacted.
- **Action taken:** Upgraded cryptography from 46.0.4 to 46.0.5 in `uv.lock`.

## Node.js Vulnerabilities

### GHSA-mw96-cpmx-2vgc — rollup (FIXED)

- **Package:** rollup (transitive dependency of vite)
- **Severity:** High
- **Affected range:** >=4.0.0 <4.59.0
- **Installed version:** 4.57.1
- **Fixed version:** 4.59.0
- **Description:** Rollup 4 has an Arbitrary File Write vulnerability via Path Traversal (CWE-22).
- **Action taken:** Updated rollup from 4.57.1 to 4.59.0 via `npm audit fix` in `twag/web/frontend/`.

## Outdated Node.js Packages (non-security)

These packages have newer versions available but no known security advisories. Updates are optional.

| Package | Current | Wanted | Latest | Notes |
|---------|---------|--------|--------|-------|
| @biomejs/biome | 2.3.14 | 2.4.7 | 2.4.7 | Dev dependency, minor update |
| @tailwindcss/vite | 4.1.18 | 4.2.1 | 4.2.1 | Dev dependency, minor update |
| @tanstack/react-query | 5.90.20 | 5.90.21 | 5.90.21 | Patch update |
| @types/react | 19.2.13 | 19.2.14 | 19.2.14 | Patch update |
| @uiw/react-codemirror | 4.25.4 | 4.25.8 | 4.25.8 | Patch update |
| @vitejs/plugin-react | 4.7.0 | 4.7.0 | 6.0.1 | Major version jump, needs evaluation |
| lucide-react | 0.469.0 | 0.469.0 | 0.577.0 | Major version jump, needs evaluation |
| react-router | 7.13.0 | 7.13.1 | 7.13.1 | Patch update |
| tailwind-merge | 2.6.1 | 2.6.1 | 3.5.0 | Major version jump, needs evaluation |
| tailwindcss | 4.1.18 | 4.2.1 | 4.2.1 | Dev dependency, minor update |
| vite | 6.4.1 | 6.4.1 | 8.0.0 | Major version jump, needs evaluation |

## Recommendations

1. **No further action required** for security — both identified vulnerabilities have been patched.
2. Consider updating minor/patch-level Node.js dependencies in a separate PR for general maintenance.
3. Major version bumps (@vitejs/plugin-react 6.x, lucide-react 0.577, tailwind-merge 3.x, vite 8.x) should be evaluated individually for breaking changes before upgrading.
