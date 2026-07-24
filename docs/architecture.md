# Target architecture (greenfield — nothing built yet)

## System shape

```
┌─────────────────────────────┐        ┌──────────────────────────────────┐
│ apps/web  (Next.js, Vercel) │  HTTP  │ services/engine (FastAPI, Railway)│
│  UI screens S1–S13          │───────▶│  /api/* — envelope responses      │
│  route handlers (thin BFF)  │        │                                   │
└──────────────┬──────────────┘        │  deterministic/                   │
               │ Supabase JS            │   comparators · gates · coverage  │
               ▼                        │   export blockers · audit writes  │
┌─────────────────────────────┐        │  pipeline/ (model components)     │
│ Supabase                     │◀──────│   Extractor · Retriever · Drafter │
│  Postgres + RLS (per tenant) │        │   Matcher · Score · Translator   │
│  pgvector (retrieval index)  │        │        │ Claude API (tool-use    │
│  Storage (tender docs, certs)│        │        ▼  JSON schema, G-6)      │
│  Auth (sessions, roles)      │        │  OCR provider (TODO: pick)       │
└─────────────────────────────┘        └──────────────────────────────────┘
```

## Where things live

- **Auth**: Supabase Auth. Web reads the session; engine validates the JWT on every request. Tenant ID always derives from the validated session — never from a request body (ET-6, pitfall #1).
- **Tenancy**: RLS policies on every table keyed by `tenant_id`; retrieval queries (pgvector) filtered by tenant before similarity. Isolation tests live in CI (PRD ET-6 "isolation tests in CI").
- **Deterministic vs AI split** (PRD §2.4, normative): everything that *decides* — eligibility comparators, gate logic, coverage counts, export blockers, financial transclusion — is plain Python in `services/engine/app/deterministic/`, unit-tested to 100% of gate ACs. Model components live in `services/engine/pipeline/`, each with: prompt file, output JSON schema, confidence field, retry cap 1, timeout, deterministic fallback.
- **Documents**: uploaded to Supabase Storage; engine pulls, OCRs (quality gate A-FR6), parses, extracts. Extraction results are TOM candidates until human-confirmed and locked (A-FR4/5). Locked TOMs are immutable rows; corrigenda create diff records.
- **Audit trail** (E-FR4): append-only `audit_events` table written by the engine on every content change, verdict override, watermark removal, export. No update/delete grants.

## Request lifecycle — core journey (upload → verdict)

1. Web S3 uploads file → route handler streams to Supabase Storage → `POST /api/tenders` registers it
2. Engine job: OCR → quality gate (≥98% else EC-1 manual-review state) → structure parse → Extractor emits schema-valid criteria with confidence + source anchors
3. Sub-0.80 items land in the verification queue (S4); human confirms; `POST /api/tenders/:id/lock` runs the deterministic lock gate (A-AC5)
4. `POST /api/tenders/:id/analyze`: criterion router types each criterion → deterministic comparators (numeric/date/bool) or Matcher (fuzzy, <0.75 → Needs-review, C-AC5) → verdicts + gap analysis persisted → S7 renders

## Folder-to-surface map

| Path | Surface | Verifier |
|---|---|---|
| `apps/web/` | web | `/verify`, `/design-review` |
| `services/engine/app/` | backend | `/verify-api` |
| `services/engine/pipeline/`, `prompts/`, `evals/` | AI | `/evals` |
| `design/`, `docs/DESIGN_SPEC.md` | design contract | `/design-review` (read-only source of truth) |
