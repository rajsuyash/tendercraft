# Conventions

## Next.js (apps/web)

- Server Components by default; `"use client"` only on files using hooks/handlers/browser APIs, placed at the leaf, never on layout/page wrappers wholesale.
- Data fetching: server components call the engine (or Supabase) directly; mutations go through **route handlers** (thin BFF) that validate input (zod) and forward to the engine. No server actions for engine-backed mutations — one mutation path, easier to audit.
- Forms: react-hook-form + zod resolver; zod schema is the single validation source, reused in the route handler.
- File layout: `app/(auth)/login`, `app/(app)/dashboard|tenders|proposals|library|profile|settings` mirroring DESIGN_SPEC routes; shared components in `components/`, C1–C6 design components in `components/design/`.

## Styling (design contract — binding)

- `design/tokens.json` is the only source of color/type/spacing values, wired into `tailwind.config.ts` `theme.extend` at M0. Hardcoded hexes and font stacks fail review.
- Verdict semantics are reserved: Pass/Fail/Needs-review render only via the semantic token pairs (`success/danger/warning` + `-bg`). Never repurpose those hues.
- Per-screen specs live in `docs/DESIGN_SPEC.md` §E; contractual selectors (`[data-empty-state]`, `[data-ai-watermark]`, `[data-transclusion]`, `[data-lock-blocked-count]`, …) are part of the design ACs — implement them verbatim.
- Keep `design/` in-repo and out of `.claudeignore`. Never overwrite `.claude/commands/design-review.md` (stitch-ux-designer owns it).
- Every screen implements default + loading (skeletons, not bare spinners) + empty + error states per §E — a blank region on a reachable state is a design-review FAIL.

## FastAPI (services/engine)

- Response envelope (LOCKED): `{ ok, data, error: { code, message } }` — every endpoint, including errors. Stack traces never leave the process; log them, return the envelope.
- Error taxonomy: `code` is a stable string (`TENANT_MISMATCH`, `OCR_QUALITY_GATE`, `LOCK_BLOCKED`, `EXPORT_BLOCKED`, `ESTIMATE_SUPPRESSED`…) — the web UI switches on it.
- Validation at the boundary: Pydantic v2 models on every request body; tenant ID from the validated JWT, never from the body.
- Async policy: handlers async; OCR/extraction run as background jobs (start with FastAPI BackgroundTasks + a `jobs` table; move to a queue when volume demands — noted ceiling).
- Deterministic modules (`app/deterministic/`) are pure functions over typed inputs — no model imports allowed there (enforce with a lint rule / import check in CI).

## AI components (services/engine/pipeline)

- Prompts live in `services/engine/prompts/<component>.md` — files, never string literals.
- One model-client module (`pipeline/client.py`): retry cap 1, explicit timeout, token/cost logged per call.
- Every model output is schema-validated (tool-use JSON schema) before use → on failure: one retry, then deterministic fallback (queue for human / explicit flag). Never crash, never invent (G-5).
- Confidence is a first-class output field; thresholds (0.80 extraction, 0.75 matcher) are constants in one module, cited to the PRD.
- Tender text is untrusted (G-6): extraction runs with allowlisted output schema; no tool other than the schema emitter; document content never parameterizes a fetch or shell.

## General

- Naming: camelCase TS, snake_case Python, PascalCase components, UPPER_SNAKE constants.
- Tests colocated: `*.test.ts` beside source (web), `tests/` mirror (engine). Fixture data under `fixtures/`, referenced by FIX-ids from docs/PRD.md §10.
- Imports: std/lib → third-party → internal, alphabetized within groups.
- Currency in UI: Indian format (₹10 Cr, ₹2,40,000); dates DD/MM/YYYY; FYs as FY23–FY25 — format helpers in `apps/web/lib/format.ts`, never ad-hoc.
