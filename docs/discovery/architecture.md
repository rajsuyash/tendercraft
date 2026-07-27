# Discovery & Traceability — architecture (target; nothing built yet)

Additive to `docs/architecture.md`. Same processes, same database, same envelope — Modules F and G are new packages inside the existing bidder engine and new routes inside the existing web app. Nothing here crosses the F13 wall.

## Shape

```
  T3 email ──▶ POST /api/inbound/email ──┐        (authenticated webhook — NOT in app/discovery)
  T1/T2   ──▶ app/discovery/fetch.py ────┤         robots · UA · rate cap · byte cap · SSRF hops
  T4 paste──▶ POST /api/opportunities ───┤
                                         ▼
                        app/discovery/sources/*.py   one adapter per source, registry-listed
                                         │  emits the normalized record (F-FR1) + raw snapshot
                                         ▼
                        app/deterministic/discovery.py
                          merge (exact portal_ref_no ONLY)   ── F-FR6 / F-AC4
                          rule evaluation → in_scope | excluded(rule) ── F-FR9 / G-9
                          duplicate-candidate grouping (suggestion, never a merge)
                                         │
                    ┌────────────────────┴────────────────────┐
                    ▼                                          ▼
      pipeline/opportunity.py                    app/deterministic/eligibility.py
        relevance band + cited match               Depth-1 verdicts — the SAME comparators
        3-line cited summary                       Depth-2 already uses (C-FR8)
        (ranks and describes; never excludes)
                    └────────────────────┬────────────────────┘
                                         ▼
                              GET /api/opportunities  →  S14 feed
```

Module G is simpler and has no external surface:

```
  locked TOM ──▶ app/deterministic/matrix.py ──▶ rows + unmapped-sentence denominator (G-FR2)
                          │                                        │
                          ├──▶ xlsx export / import diff ──────────┤ app/matrix_export.py
                          └──▶ coverage(), the ONE function ───────┴──▶ matrix · export gate · dashboard
                                                                        (G-FR7)
  approved response ──▶ answer library index (pgvector, tenant-filtered) ──▶ suggestion + provenance
```

## Where the decisions live

- **Deterministic (`app/deterministic/`)**: merge, rule evaluation, feed partition, matrix generation, the unmapped denominator, coverage, import-conflict detection, Depth-1 and Depth-2 eligibility comparators. No model imports — CI-enforced, and additionally named by `tools/check-discovery-guardrails.sh` so a failure reads as the right thing.
- **Model (`pipeline/`)**: relevance banding, opportunity summarisation, eligibility-subset extraction, requirement-sentence identification, prior-answer retrieval ranking. All schema-validated, all confidence-scored, all with a deterministic fallback. None of them may remove an item from anything.
- **Adapters (`app/discovery/sources/`)**: parsing only. An adapter that cannot parse a field emits `null` — it never asks a model to fill a field a deterministic filter will read. That single rule is what keeps G-9 true in practice: if a model can populate `estimated_value`, it can move an item past a value-band rule, and the exclusion path becomes model-driven through the back door.

## Request lifecycles

**Discovery (T3, the first path built).** Portal alert email → forwarding address → provider parse → `POST /api/inbound/email` (signature verified) → adapter normalizes → raw snapshot stored → deterministic merge → rule partition → in_scope items queued for relevance + Depth-1 triage → feed. Target: visible within 15 minutes (F-FR3).

**Discovery (T1/T2).** Scheduler wakes a source → registry supplies base URL, tier, cadence, parser fingerprint → guarded fetch (robots, UA, rate cap, byte cap, SSRF hop resolution) → same path from "adapter normalizes" onward. Item-count deviation vs. the trailing median raises a **source-health incident** rather than producing an empty feed (EC-8).

**Triage escalation (C §4.1).** Listing fields → comparators, zero model calls. Fields missing → fetch the NIT, extract only the eligibility subset from targeted pages. Still unresolved → `Unknown — needs the NIT`. Full base-Module-A ingestion happens only on user action or above a configured value threshold, capped per workspace-day.

**Matrix.** TOM lock → deterministic generation → rows + unmapped set → user resolves unmapped → matrix usable in-app or as XLSX. Re-import diffs per row; requirement text, level and anchor are import-protected so a spreadsheet can never rewrite a locked TOM.

## Data model additions (all workspace-scoped, all RLS + isolation-tested)

`sources` (registry mirror + health) · `opportunities` (normalized record, merge key, bucket, assignee) · `opportunity_sources` (many-to-one provenance, F-FR8) · `opportunity_rules` (named, user-authored) · `opportunity_snapshots` (raw, retrieval-stamped) · `matrix_rows` · `matrix_unmapped` · `answer_library` (+ outcome linkage).

`opportunities` → `tenders` is a nullable FK: an opportunity becomes a tender only on ingest, and the tender keeps its origin. Nothing about the base tender flow changes for a manually uploaded tender.

## Folder-to-surface map (extends `docs/architecture.md`)

| Path | Surface | Verifier |
|---|---|---|
| `services/engine/app/discovery/` | acquisition | `/verify-api`, `pnpm guardrails` |
| `services/engine/app/deterministic/discovery.py`, `matrix.py` | gates | `uv run pytest` (100% branch) |
| `apps/web/app/(app)/opportunities/` | web | `/verify-discovery`, `/design-review S14..S16` |
| `apps/web/app/(app)/tenders/[id]/matrix/` | web | `/verify-discovery matrix`, `/design-review S17` |
| `services/engine/evals/discovery/` | AI | `/evals` + the F-AC1 replay harness |
