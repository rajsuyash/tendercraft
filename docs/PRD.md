# TenderCraft — Execution Layer (scaffold wrapper)

The **product PRD is [`../tendercraft-PRD.md`](../tendercraft-PRD.md)** — read it for modules A–E, ACs, guardrails, edge cases. It is sha-pinned by `docs/DESIGN_SPEC.md` §I and must never be edited by an agent (propose edits to the human).

This file supplies the execution-layer sections a prd-builder v3 PRD would carry. Stubs marked `TODO:` need human input — recommend running **prd-builder in Upgrade mode** to fill them properly.

## §0 Agent contract

- Work one milestone at a time (§5); `/plan` derives tasks; never pull later-milestone work.
- `TODO:` markers stop the session and ask the human. `ASSUMPTION` proceeds and is restated in the summary.
- Non-goals (never build): portal write integration / autonomous submission (G-1), credential fabrication (G-7), cross-client training without opt-in (§6), removal of watermark/audit paths.
- The PRD §2.4 AI-vs-deterministic table is normative: model output crossing into the deterministic column is a defect, not a shortcut.
- Design contract: UI tasks carry `design_ref` (S-ids from DESIGN_SPEC §D); reference render + tokens are opened before UI code; `/design-review` verifies.

## §4 Stack & decisions

| Decision | Status | Value |
|---|---|---|
| Web | LOCKED | Next.js 15 App Router + TypeScript + Tailwind (tokens) + shadcn/ui, pnpm |
| Engine | LOCKED | Python 3.12 + FastAPI, uv |
| DB/tenancy | LOCKED | Supabase Postgres, RLS per tenant (ET-6), pgvector, Supabase Storage |
| LLM | LOCKED | Claude API — sonnet (extract/draft), haiku (classify/route); tool-use JSON schema outputs |
| Deploy | ASSUMPTION | Vercel (web) + Railway (engine). India-region residency (PRD §9) is a PH2 compliance gate — revisit before real customer data. |
| OCR provider | TODO: pick (Google Document AI vs AWS Textract vs Surya) — PRD A-FR1/A-FR6 needs ≥98% word-accuracy estimation |
| Auth | ASSUMPTION | Supabase Auth, email+password now; SSO Enterprise later (E-FR1) |
| Response envelope | LOCKED | `{ ok: boolean, data: T | null, error: { code, message } | null }` — all engine + route-handler responses |

## §5 Build sequence (derived from PRD §10 roadmap)

| M | Scope | Exit criteria (demoable) |
|---|---|---|
| M0 | Walking skeleton: monorepo boots, web :3000 renders S1+S2 shells from tokens, engine :8000 `/health`, Supabase schema v0 (tenants, users, tenders), seed + fixtures, verifiers proven (/verify, /verify-api, /evals harness on starter cases) | All commands in CLAUDE.md run green; S2 empty state passes S2-D2 |
| M1 | Module A ingestion: upload → parse → extract (Extractor v0) → verification queue → TOM lock. Screens S3, S4, S5 | A-AC3/A-AC5 deterministic gates pass; extractor starter evals run; S4-D1 passes |
| M2 | Module C analyzer: vendor profile, criterion router, deterministic comparators, fuzzy matcher, verdict dashboard. Screens S6, S7 | C-AC4/C-AC5 gates pass; S7-D1..D3 pass; gap analysis renders quantified shortfalls |
| M3 | Module B generator core: content library, retrieval (validity hard-filter), drafter with cite-or-flag, review workspace. Screens S8, S9 | B-FR1/2/3 enforced in UI (S9-D1..D3); citation validator green |
| M4 | Module E + export: approvals, audit trail, compliance matrix, export gate, DOCX/PDF. Screens S10, S12 | E-AC2/B-AC4 hard gates pass; S10-D1..D3 pass |
| M5 | Module D estimator (data-gated): score range, suppression, weak sections. Screen S11 | D-AC4 suppression fires; S11-D1..D3 pass |

TODO: per-milestone feature specs with individual AC verify-tags (prd-builder Upgrade mode fills this).

## §6 Routes (canonical — from DESIGN_SPEC §I, derived from PRD UX flows)

| Route | Screen | Engine endpoints (v0 sketch) |
|---|---|---|
| /login | S1 | Supabase auth |
| /dashboard | S2 | GET /api/dashboard |
| /tenders/upload | S3 | POST /api/tenders (upload), GET /api/tenders/:id/status |
| /tenders/:id/verify | S4 | GET/POST /api/tenders/:id/criteria, POST /api/tenders/:id/lock |
| /tenders/:id | S5 | GET /api/tenders/:id (TOM), GET /api/tenders/:id/corrigenda |
| /profile | S6 | GET/PUT /api/profile |
| /tenders/:id/analysis | S7 | POST /api/tenders/:id/analyze, GET /api/tenders/:id/analysis |
| /library | S8 | GET/POST /api/library, POST /api/library/:id/confirm-class |
| /proposals/:id | S9 | POST /api/proposals, GET/PATCH /api/proposals/:id, POST /api/proposals/:id/generate |
| /proposals/:id/export | S10 | GET /api/proposals/:id/compliance-matrix, POST /api/proposals/:id/export |
| /proposals/:id/score | S11 | POST /api/proposals/:id/estimate |
| /settings | S12 | GET/PUT /api/workspace/* |
| /error | S13 | — |

TODO: per-endpoint request/response contracts + error cases (prd-builder Upgrade mode).

## §9 Environment inventory

See `.env.example` — names only. TODO: confirm OCR provider vars once chosen.

## §10 Fixtures

| ID | Fixture | Purpose |
|---|---|---|
| FIX-1 | Test user `priya@meridian.test` / seeded password, role Admin+Approver, tenant "Meridian Infotech Pvt Ltd" | browser-verifier signs in as this user |
| FIX-2 | Seeded vendor profile matching DESIGN_SPEC §E data (₹8.2 Cr avg turnover, expired ISO 9001, Udyam MSE) | drives S6/S7 verdict + gap states |
| FIX-3 | Sample tender package (GEM/2026/B/5127401 fixture PDF, ~20pp) + pre-extracted criteria JSON incl. 3 sub-0.80 items | drives S3/S4/S5 without live OCR |
| FIX-4 | Content library docs (turnover cert, expired ISO cert, completion certs) with structured fields | drives S8/S9 citation + expiry states |
| FIX-5 | Proposal with 1 placeholder + 1 unverified sentence + pending approval | drives S9/S10 blocker states |

`pnpm seed` resets all fixtures idempotently. TODO: author the actual fixture files in M0.
