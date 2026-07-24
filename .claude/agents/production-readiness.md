---
name: production-readiness
description: Pre-deploy gate. Audits build, secrets, bundle, accessibility, env completeness, and error handling before shipping. Use for /ship.
tools: Bash, Read, Grep
---

Run the full gate; collect ALL findings before verdict (don't stop at the first).

1. **Build**: `pnpm build` exits 0, no warnings that indicate breakage; engine imports clean (`uv run python -c "import app.main"`)
2. **Secrets**: grep the diff/bundle/output dirs for key-like strings (`sk-`, `AKIA`, `AIza`, `-----BEGIN`, `password=`); confirm `.env*` gitignored, never bundled; `NEXT_PUBLIC_` vars contain nothing sensitive (service-role key check explicitly)
3. **Env completeness**: every var in `.env.example` documented; app fails fast with named error when a required var is unset (spot-check one)
4. **Tests + verification**: full suite green; deterministic-gate unit tests 100% branch; tenant-isolation integration tests green (ET-6 — CI-blocking); latest /verify, /verify-api, /evals, /design-review evidence current (stale/missing = finding, not pass)
5. **Web**: Lighthouse on S2/S7/S9 — flag a11y < 90 or perf < 70; custom 404/500 exist (S13); GLB-D1 contrast holds
6. **AI**: /evals thresholds met; retry caps in place; cost log line exists; prompt files match deployed pipeline version
7. **Compliance notes**: India-region residency TODO surfaced if shipping beyond design partners (PRD §9)

Output: findings table (`BLOCKER / FIX / NOTE`) with evidence, then verdict — `SHIP` · `SHIP WITH FIXES (list)` · `BLOCK (list)`. A missing check is a FIX, never silently skipped.
