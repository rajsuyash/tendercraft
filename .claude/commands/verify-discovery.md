---
description: Browser-grounded verification for Modules F and G (opportunity feed, triage, compliance matrix) via the browser-verifier subagent.
argument-hint: [route, feature (F-AC6), screen (S14), "matrix", or "all"]
---

Delegate to the **browser-verifier** subagent. This is the BIDDER app (`apps/web`) — not `apps/evaluate`.

Scope: $ARGUMENTS if given; otherwise derive affected routes from the current diff mapped through `docs/discovery/PRD.md` §6. `"all"` = S14–S18. `"matrix"` = S17 only.

Preconditions: web dev server on http://localhost:3000 (BLOCKED if down — do not start it); seed via `pnpm seed` if FIX-6..FIX-10 records are missing. Sign in as FIX-1 (`priya@meridian.test`).

**Fixture choice is not interchangeable:**
- **F-AC4 (zero wrong merges) runs against FIX-7**, which contains a deliberate near-miss pair — same authority, same closing date, *different tender*. Run this AC on the duplicate trio alone and it proves nothing, because merging is what that trio is supposed to do.
- **F-AC6 runs against FIX-8**, which ships the exact expected in-scope/excluded partition for its three rules. Assert the partition, not just that a count rendered.
- **G-AC1 runs against FIX-10**, whose requirement sentences deliberately hide in a table cell, a footnote and an annexure reference. A shredder tuned on prose reports a comfortable zero unmapped — which is the exact bug the denominator exists to catch.

**Two assertions this module needs that the base app does not.** Both concern data that must not exist, so DOM-only checking is insufficient — inspect the **network responses**:

1. **F-AC6 / G-9 — nothing hidden except by a named user rule.** Every item returned for `GET /api/opportunities?bucket=excluded` must carry a non-null `rule_id` naming a user-authored rule. An item excluded for any other reason is a guardrail breach, and it renders identically to a legitimate one — the DOM cannot tell you.
2. **C-AC10 — a provisional verdict never becomes a recommendation.** For any opportunity whose `eligibility_depth` is 1, no Bid/No-Bid field may appear in any network or RSC payload. A DOM-only check passes when the card is merely hidden.

Also assert, at the DOM level: the Excluded count is visible from the primary feed without opening a menu (S14-D2); every feed row carries a resolvable source link and retrieval timestamp (S14-D3, F-AC7); relevance renders as a band with its cited past project, never a bare number (S14-D4); Depth-1 verdicts carry a visible provisional label (S15-D1); the unmapped-sentence chip blocks while > 0 (S17-D1).

Paste the subagent's verdict table + SUMMARY verbatim, then screenshot paths. Any FAIL → fix and re-run on the failed scope before claiming done.

Note: `/verify-discovery` covers user-visible behaviour only. The acquisition-side guardrails (G-8, G-9, G-10) are verified by `pnpm guardrails`, and the module's primary gate (F-AC1 recall) by the replay harness in `evals/discovery/replay/`. A green run here says nothing about either.
