---
description: Browser-grounded verification for TenderCraft EVALUATE (apps/evaluate) via the browser-verifier subagent.
argument-hint: [route, feature (F7), journey (J1), or "all"]
---

Delegate to the **browser-verifier** subagent. This is the GOVERNMENT-side app — not `apps/web`.

Scope: $ARGUMENTS if given; otherwise derive affected routes from the current diff mapped through `docs/evaluate/PRD.md` §6 → `tendercraft-evaluate-PRD.md` §2.5. "all" = every route in §2.5.

Preconditions the subagent must respect: evaluate dev server on http://localhost:3001 (BLOCKED if down — do not start it); seed via `pnpm seed:evaluate` if FIX records are missing.

**Fixture tenant matters and is not interchangeable:**
- **Journey ACs (J1-*, J2-*) run against tenant A (empty), FIX-1 `officer@empty.test`.** A journey AC executed on a seeded account tests nothing about first-run — if the subagent runs these on tenant B, the result is void.
- Feature ACs run against tenant B (seeded), FIX-2 `officer@authority.test`.
- Member-scoped ACs sign in as a FIX-3 member, not an officer.

**Two assertions this app needs that the bidder app does not.** Both are about data that must not exist, so DOM-only checking is insufficient — inspect the network responses:
1. **F9 / J1-AC3 — sealed bids.** Before technical lock, no financial figure may appear in the DOM *or any network/RSC payload*, and `GET /api/evaluations/:id/financial` must return `409 FINANCIAL_SEALED`.
2. **F7-AC3 — blind-first scoring.** The AI-proposed mark must be absent from the DOM *and every network response* until the evaluator's own mark is recorded.

Paste the subagent's verdict table + SUMMARY verbatim, then screenshot paths. Any FAIL → fix and re-run on the failed scope before claiming done.
