# Test strategy

**The rule: an AC is verified at its tagged layer only.** Passing unit tests never satisfies a browser-verify AC; a green eval never satisfies a deterministic-gate AC. Browser and integration layers assume `pnpm seed` has run (fixtures FIX-1..5, docs/PRD.md §10).

| Layer | Owner | Covers |
|---|---|---|
| unit | `pnpm test` (Vitest) · `uv run pytest` | format helpers, components, **all deterministic engines** — comparators, lock gate (A-AC5), coverage counts (B-AC2), export blockers (B-AC4/E-AC2), suppression gate (D-AC4), anchor validator (A-AC3), verdict-rationale validator (C-AC4). Gate ACs get exhaustive unit coverage — they are the product's safety story. |
| integration | `uv run pytest` (API tests) + `/verify-api` live smoke | endpoint contracts vs docs/PRD.md §6 envelope, error taxonomy, authz (tenant from JWT), audit-event writes (E-AC1), **tenant-isolation tests** (ET-6 — a seeded tenant-B must never appear in tenant-A responses or retrievals; CI-blocking) |
| browser-verify | browser-verifier via `/verify` (Playwright MCP) | user-visible flows on S1–S13 routes; signs in as FIX-1; console/network cleanliness |
| design-review | `/design-review` (stitch-ux-designer contract) | S#-D# + GLB-D# design ACs from docs/DESIGN_SPEC.md §H — DOM assertions on contractual selectors, breakpoint screenshots, token conformance |
| evals | eval-runner via `/evals` (golden sets in `services/engine/evals/`) | Extractor recall/precision (A-AC1), classification F1 (A-AC2), matcher confidence routing (C-AC5 — sub-0.75 never auto-Pass), citation validity (B-AC3), fault-injection fallbacks. Starter sets are marked `"starter": true` — expand from the annotation corpus before trusting scores as release gates. |
| manual | human sign-off, listed explicitly | D0/Gate D design taste (done) · OCR provider accuracy validation on real scans (M1) · DPDP/residency compliance review (PH2) · any watermark-removal / admin-override UX |

## Eval discipline

- Golden sets are fixtures: never edit a case, label, or threshold to make a run pass. Threshold changes are human PRD edits.
- No exact-text assertions on generative output — assert schema, fields, thresholds.
- PRD §5.3 release rule applies from M1: any gate metric regressing > 2 points on gold sets blocks the change; prompt diffs require `/evals` before done.

## Coverage target

80% line coverage on `apps/web` and `services/engine/app`; **100% branch coverage on `app/deterministic/`** (the gates). Pipeline model wrappers are covered by evals + fault-injection, not line-coverage theater.
