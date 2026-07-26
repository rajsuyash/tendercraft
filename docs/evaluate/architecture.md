# TenderCraft Evaluate — target architecture (nothing built yet)

## The shape, and the one line that matters

```
┌──────────────────────────────┐        ┌───────────────────────────────────┐
│ apps/evaluate (Next.js)      │  HTTP  │ services/evaluate-engine (FastAPI) │
│  officer + TEC member UI     │───────▶│  /api/* — envelope responses       │
└───────────────┬──────────────┘        │                                    │
                │                       │  evaluate/deterministic/           │
                ▼                       │   screening · qualification        │
┌──────────────────────────────┐        │   sealed-bid gate · QCBS · quorum  │
│ Supabase project "evaluate"  │◀───────│  evaluate/pipeline/                │
│  Postgres + RLS per authority│        │   extractor · evidence locator     │
│  Storage (bids, sealed)      │        │   score-proposer                   │
│  Auth (own identity pool)    │        └───────────────────────────────────┘
└──────────────────────────────┘
        ╔══════════════════════════════════════════════════════════╗
        ║  ▲ NO PATH ACROSS THIS LINE — F13, enforced in CI         ║
        ╚══════════════════════════════════════════════════════════╝
┌──────────────────────────────┐        ┌───────────────────────────────────┐
│ Supabase project "bidder"    │        │ services/engine (bidder)          │
└──────────────────────────────┘        └───────────────────────────────────┘
```

Different database. Different auth pool. Different model credential. Shared: design tokens, CI
patterns, container patterns, and the conventions in this folder. Nothing else, ever.

## Why the package is `evaluate/` and not `app/`

The bidder engine's package is `app/`. If this one were also `app/`, `from app.db import …`
inside the evaluate engine would be ambiguous to a reader and invisible to a grep — and the
first version of `tools/check-wall.sh` proved it, reporting "wall: intact" on a planted
cross-import because it had excluded the very directory it meant to inspect. A distinct package
name makes the breach unambiguous and the check trivial.

## Where things live

- **Tenancy.** One authority = one workspace = one department ("Corporation — IT" and
  "Corporation — Roads" are two authorities). This reuses the bidder-side multi-workspace model
  and its hardened RLS, which is the whole reason for choosing it: that code already survived a
  Sev-1 and a live isolation suite.
- **Sealed envelopes.** `bid_financials` is a separate table from `bids`, written at ingest.
  Its RLS policy keys on the evaluation's technical-lock state, so the seal holds even against a
  query that forgets to check. Defence in depth: the gate exists in the policy, the handler, and
  an integration test.
- **Deterministic vs AI.** `evaluate/deterministic/` decides; `evaluate/pipeline/` reads and
  drafts. The CI job forbids model imports in the former and demands 100% branch coverage.
- **Scores are append-only in spirit.** A submitted member mark is never mutated. Consensus is a
  separate row (`consensus_marks`) so the individual views that justified it survive into the
  report.
- **Audit.** `audit_events` append-only, UPDATE/DELETE revoked at the database level. The bidder
  side already proved this trigger refuses even the service role — which is why erasure is a
  documented out-of-product process rather than a feature.

## Request lifecycle — the gate

1. Officer uploads bids → engine splits technical/financial at ingest → financial rows written
   sealed, never returned.
2. Members score independently; the AI proposal is withheld until the member's own mark is
   recorded (F7-AC3, asserted against the network response, not just the DOM).
3. Chair resolves variance-flagged criteria with a recorded consensus mark, then locks.
4. **Only now** does `GET /api/evaluations/:id/financial` stop returning `409 FINANCIAL_SEALED`.
5. QCBS combination → ranking → a tie, if any, blocks finalisation until a human records the
   published rule.

## Folder-to-verifier map

| Path | Surface | Verifier |
|---|---|---|
| `apps/evaluate/` | web | `/verify-eval` |
| `services/evaluate-engine/evaluate/` | backend | `/verify-eval-api` |
| `services/evaluate-engine/{prompts,evals}/` | AI | `/evals` |
| `tools/check-wall.sh` | the wall | CI, every push |
