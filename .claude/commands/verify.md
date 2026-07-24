---
description: Run browser-grounded verification on affected routes via the browser-verifier subagent.
argument-hint: [route, screen (S7), or "all"]
---

Delegate to the **browser-verifier** subagent.

Scope: $ARGUMENTS if given; otherwise derive affected routes from the current diff mapped through `docs/PRD.md` §6. "all" = every route S1–S13.

Preconditions the subagent must respect: dev server on http://localhost:3000 (BLOCKED if down — do not start it); seed fixtures via `pnpm seed` if FIX records are missing; auth'd routes sign in as FIX-1.

Paste the subagent's verdict table + SUMMARY verbatim into your response, then screenshot paths. Any FAIL → fix and re-run /verify on the failed scope before claiming done. For design ACs on the same screens, run `/design-review` separately.
