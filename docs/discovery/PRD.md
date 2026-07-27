# Discovery & Traceability — Execution Layer (Modules F, G + C delta)

The **product PRD is [`../../tendercraft-discovery-PRD.md`](../../tendercraft-discovery-PRD.md)** — read it for modules F/G, the Module C triage delta, ACs, guardrails G-8..G-10, error tolerances ET-7..ET-9, and edge cases EC-8..EC-13. It **extends** `tendercraft-PRD.md`; every base doctrine still applies.

This file supplies the execution layer: milestones, routes, endpoints, env, fixtures. It sits beside `docs/PRD.md` (the base execution layer) and does not replace it.

## §0 Agent contract (additions to `docs/PRD.md` §0)

- These modules live **inside the existing bidder surfaces** (`apps/web`, `services/engine`). There is no new app, no new engine, no new database, and no new CLAUDE.md. `tools/check-wall.sh` still governs the bidder/evaluate boundary and is unaffected.
- `tools/check-discovery-guardrails.sh` is CI-blocking and ships **before** the first adapter. It is not advisory and it is not a lint rule — see `docs/discovery/conventions.md` §Guardrails.
- Non-goals, unchanged from the base and reinforced here: no authenticated acquisition, no CAPTCHA bypass, no IP rotation, no portal write path of any kind (G-1, G-8).
- Any discovery source added without a registry entry recording its tier and terms-review date is a defect, not an oversight.

## §5 Build sequence

Maps the product PRD's PH4a–e onto this repo's milestone numbering. Work one at a time; never pull later-milestone work.

| M | Phase | Scope | Exit criteria (demoable) |
|---|---|---|---|
| M6 | PH4a | **Module G core.** Matrix generated on TOM lock, unmapped-sentence denominator, row ownership/status, XLSX export + import with row-level diff. No new external dependency. | G-AC1–5, G-AC8–9 pass; S17 design ACs pass; `/verify-discovery matrix` green |
| M7 | PH4b | **Module F via T3 only.** Per-workspace inbound address, email parse → normalized record, dedup, named rules, feed, daily digest, assignment. Zero crawling. | F-AC3–F-AC7 pass on email-sourced items; S14/S16 design ACs pass; guardrail script green with adapters absent |
| M8 | PH4c | **Module C delta.** Eligibility-only extractor, Depth-1 triage on feed items, escalation policy + cost cap, profile-change replay, gap rollup. | C-AC6–C-AC11 pass; S15/S18 design ACs pass |
| M9 | PH4d | **T1/T2 adapters.** NIC-stack adapter family + GeM/CPPP public search, source registry with terms-review dates, guarded fetcher, source-health incidents, corrigendum watch. | F-AC1 ≥ 95% on the replay harness; F-AC5, F-AC8 pass; `pnpm guardrails` green with adapters present |
| M10 | PH4e | **Answer library.** Approved responses indexed per requirement with outcome linkage; suggestion → explicit acceptance. | G-AC6–G-AC7 pass; ≥ 40% suggestion acceptance on the partner cohort |

**Sequencing rationale** (from the product PRD §13): G first because it needs no external dependency and turns the existing locked TOM into a standalone deliverable. T3 email before crawling because it carries no ToS exposure and lets dedup and ranking be tuned on real volume before a crawler exists. F-AC1's backtest needs 12 months of partner bid history — **recruit for it during M6**, because M9 has no exit gate without it.

## §6 Routes (canonical — extends `docs/DESIGN_SPEC.md` §I)

| Route | Screen | Engine endpoints |
|---|---|---|
| /opportunities | S14 | `GET /api/opportunities?bucket=in_scope\|excluded\|all&cursor=` · `GET /api/sources/health` |
| /opportunities/:id | S15 | `GET /api/opportunities/:id` · `POST /api/opportunities/:id/watch` · `POST /api/opportunities/:id/assign` · `POST /api/opportunities/:id/triage` · `POST /api/opportunities/:id/ingest` |
| /opportunities/rules | S16 | `GET/POST /api/opportunity-rules` · `PUT/DELETE /api/opportunity-rules/:id` · `POST /api/opportunity-rules/preview` |
| /tenders/:id/matrix | S17 | `POST /api/tenders/:id/matrix` (generate) · `GET /api/tenders/:id/matrix` · `PATCH /api/tenders/:id/matrix/rows/:rowId` · `GET /api/tenders/:id/matrix/export.xlsx` · `POST /api/tenders/:id/matrix/import` |
| /profile/gaps | S18 | `GET /api/profile/gaps` |
| — (no UI) | — | `POST /api/inbound/email` — T3 webhook, shared-secret authenticated, **not** under `app/discovery/` (see conventions §Guardrails) |

Envelope rule unchanged: `{ ok, data, error: { code, message } }` on every endpoint including errors. `GET .../matrix/export.xlsx` returns **bytes** on 2xx — the same documented deviation as the DOCX export in `docs/conventions.md`; every error path still returns the envelope.

New error codes: `SOURCE_DEGRADED`, `RULE_INVALID`, `MATRIX_UNMAPPED_REMAIN`, `MATRIX_IMPORT_CONFLICT`, `TRIAGE_NEEDS_NIT`, `TRIAGE_CAP_REACHED`, `INBOUND_UNVERIFIED`.

Pagination: every list endpoint is cursor-paginated on the full `(created_at, id)` sort tuple with a `Z`-suffixed timestamp — see `docs/known-pitfalls.md`; the feed is the highest-volume list this product has and will hit both traps.

## §9 Environment inventory

Names in `.env.example` under the DISCOVERY block. Fail fast on missing required vars with a named error — no silent fallbacks, and specifically no default user agent (an unidentified crawler is a G-10 breach, so its absence must stop the process rather than degrade).

| Var | Purpose |
|---|---|
| `DISCOVERY_INBOUND_DOMAIN` | domain for per-workspace T3 addresses |
| `DISCOVERY_INBOUND_SECRET` | shared secret verifying the inbound-email webhook |
| `DISCOVERY_USER_AGENT` | identified UA string (G-10) — required, no default |
| `DISCOVERY_CONTACT_URL` | contact URL carried in the UA (G-10) — required |
| `DISCOVERY_MAX_RPS_PER_HOST` | per-host rate cap |
| `DISCOVERY_FETCH_BYTE_CAP` | per-response byte cap |
| `DISCOVERY_POLL_INTERVAL_MIN` | base poll cadence; per-source override in the registry |
| `DISCOVERY_TRIAGE_DAILY_CAP` | max Depth-1 NIT escalations per workspace per day (cost gate, §4.1) |

## §10 Fixtures (extends `docs/PRD.md` §10)

| ID | Fixture | Purpose |
|---|---|---|
| FIX-6 | Raw source corpus: 3 forwarded portal alert emails (one single-tender, one aggregator digest, one corrigendum notice) + 2 captured listing-page snapshots | drives F ingestion without network access |
| FIX-7 | Duplicate set: the same tender as it appears on a state portal, on CPPP, and in a forwarded email — plus a **near-miss pair** (same authority, same closing date, different tender) | drives F-AC3 and, critically, F-AC4 — the near-miss pair must never merge |
| FIX-8 | Rule set + expected partition: 40 opportunities, 3 named rules, and the exact in-scope/excluded split each rule produces | drives F-AC6 and the S16 preview |
| FIX-9 | Backtest replay set: ≥ 50 tenders a design partner actually bid on, with their source records | drives F-AC1 — **the primary gate; M9 cannot exit without it** |
| FIX-10 | Matrix set: a locked TOM with 47 requirements, 3 requirement sentences deliberately living in a table cell / footnote / annexure reference, and a round-trip XLSX | drives G-AC1–G-AC5 and EC-12 |

`pnpm seed` extends to reset these idempotently.

## §11 Divergence log

| Date | PRD says | Built instead | Why |
|---|---|---|---|
| 2026-07-27 | Requirement-sentence identification is a model task (product PRD §7) | Deterministic obligation-marker detection in `app/deterministic/shred.py` | Obligation is a grammatical signal, not a semantic one, and it is how a bid desk shreds by hand. A model-computed denominator changes whenever the prompt changes; an auditor can check "every sentence containing 'shall'" but not a vibe. It also costs nothing — ingest already makes one model call per page and this would have doubled it. Ceiling named in the module docstring: obligations phrased without a marker are missed, and detection errs toward over-collecting because an over-collected sentence costs one dismissal while an under-collected one is the silent omission the denominator exists to prevent. **Revisit if real NITs show a miss rate that matters.** |
| 2026-07-27 | G-AC1 blocks marking the matrix complete | Same — and deliberately NOT wired into the export gate | The shredder has no measured false-positive rate on a real 200-page NIT. Wiring an unmeasured signal into the product's hardest gate would train users to reach for the admin override. |

## §12 Open decisions

- `TODO:` per-endpoint request/response contracts for the F and G endpoints above.
- `TODO:` T1 availability per portal — the product PRD flags this as assumption #1 and **M9 scope depends on the answer**. Verify before estimating.
- `TODO:` inbound email provider choice (parse-and-POST webhook). Constraint: must expose a verifiable signature; `DISCOVERY_INBOUND_SECRET` assumes one exists.
- `ASSUMPTION:` opportunities, rules, sources and matrix rows are all workspace-scoped and carry `tenant_id` + an RLS policy + an isolation test before merge (base ET-6, non-negotiable).
