# TenderCraft Evaluate — execution layer

**Product truth: [`../../tendercraft-evaluate-PRD.md`](../../tendercraft-evaluate-PRD.md).** Read it
for features F1–F13, the 57 acceptance criteria, the journey spine and the assumptions register.
This file is the execution wrapper: what to build when, and where each verifier points.

> Sibling product: the bidder-side app (`apps/web`, `services/engine`), whose PRD is
> `../PRD.md` / `../../tendercraft-PRD.md`. **They share source patterns and zero data.**

## §0 Agent contract (mirrors PRD Section 0 — never contradict it)

- One milestone at a time. Never pull later-milestone work.
- `TODO:` → stop and ask. `ASSUMPTION` → proceed and restate in the summary.
- **AI reads and writes; code decides.** Responsiveness, qualification, a locked mark, a rank,
  and whether an envelope may open are pure functions in `evaluate/deterministic/` at 100%
  branch coverage. Model output crossing that line is a defect.
- **Sealed-bid integrity is a code gate.** Reaching financial data before technical lock by any
  path — API, direct query, export, error branch — is Sev-1.
- **The wall (F13) is architecture.** `tools/check-wall.sh` runs in CI on every push.
- Every score is attributable to a named human.

## §5 Build sequence

| M | Scope | Exit criteria |
|---|---|---|
| M0 | Walking skeleton: separate Supabase project, schema v0, auth, `/evaluations` empty state, engine `/health`, seed, `/verify-eval` proven | Empty state renders · FIX-1 signs in · **`./tools/check-wall.sh` green in CI** |
| M1 | J1.1–J1.2 — RFP upload → extraction → framework review → lock | F2-AC1..3, F3-AC1..3, **J1-AC1** |
| M2 | J1.3–J1.5 — committee + COI, bid intake, deterministic PQ screening | F4-AC1..3, F5-AC1..3, F6-AC1..4, **J1-AC2**, **J2-AC1** |
| M3 | J1.6–J1.7 — blind-first scoring, variance, consensus, quorum, technical lock | F7-AC1..6, F8-AC1..6, **J2-AC2** |
| M4 | J1.8–J1.9 — financial gate, opening, QCBS, ranking, ties | F9-AC1..4, F10-AC1..4, **J1-AC3** |
| M5 | J1.10 — evaluation report + audit export | F11-AC1..4, F12-AC1..3 |
| M6 | Hardening — recovery paths, all screen states, isolation suite in CI | All P0 ACs green |

### Throughput extension (N-series)

Product truth: [`../../tendercraft-evaluate-throughput-PRD.md`](../../tendercraft-evaluate-throughput-PRD.md)
— features F14–F28, entities E14–E26, journey J3, ENV-9..15, FIX-9..17. It extends this product;
it does not replace it. Two of the seven source pain points (TP32 committee silos, TP36 report
drafting) are **already covered by F7/F8/F11/F12 — build nothing for them.**

| M | Scope | Exit criteria |
|---|---|---|
| N1 | TP6 — bulk/ZIP intake, format normalisation, vision OCR fallback, attribution + triage | F14-AC1..4, F15-AC1..4, F16-AC1..3, **J1-AC6..8** |
| N2 | TP11 — required-document register + deterministic presence gate | F17-AC1..3, F18-AC1..4 |
| N3 | TP17 — offer extraction, requirement↔offer mapping, compliance matrix | F19-AC1..3, F20-AC1..4, F21-AC1..3 |
| N4 | TP1 — draft workspace, clause library, rulepack, past-tender signal, review + sign-off, publish | F22..F26 ACs, **J3-AC1..4** |
| N5 | TP40 — award/regret/debrief behind the disclosure gate | F27-AC1..3, F28-AC1..4, **J1-AC9** |

N1 ships triage in the same milestone as bulk upload: bulk intake without triage produces
silently mis-attributed files, which is worse than the Excel tracker it replaces.

New deterministic modules (100% branch coverage, no model in the path, import-checked in CI):
`evaluate/deterministic/presence.py`, `rulepack.py`, `disclosure.py`.

**Blocking human input before N4:** a procurement-legal read of rules R1–R10's citations and
severities (throughput PRD §12 TODO). Rules are data (`EVAL_RULEPACK_PATH`), not code.

## §6 Routes

Canonical list in PRD §2.5; API surface in PRD §6.1. Web `apps/evaluate` → `/verify-eval`;
engine `services/evaluate-engine` → `/verify-eval-api`.

## §9 Environment

`ENV-1..8` in PRD §9. Names live in `.env.example`; values never leave `.env`.
**`NEXT_PUBLIC_EVAL_SUPABASE_URL` must never equal `NEXT_PUBLIC_SUPABASE_URL`** — CI fails if it does.

## §10 Fixtures

`FIX-1..8` in PRD §10. Three tenants on purpose: **A empty** (every journey AC runs here — a
J-AC on a populated account tests nothing about first-run), **B seeded**, **C isolation probe**.
`pnpm seed:evaluate` is idempotent.
