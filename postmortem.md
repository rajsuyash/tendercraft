# Postmortem: TenderCraft build

**Shipped**: 2026-07-24 · **Milestones**: M0–M5 (6) · **Escalations**: 0 (all failures auto-resolved) · **Reviews**: 6 opus code-reviews, every cx:high task

## What worked
- **Deterministic-first**: building the safety gates (lock, comparators, export, suppression, cite-or-flag) as pure 100%-branch-tested functions BEFORE their I/O wrappers meant the product's whole "deterministic logic decides" thesis was provable offline, and the AI layers just plugged in. Model-proposes/deterministic-decides held everywhere (§2.4).
- **Live verification over vibes**: browser-driving every screen + live Supabase isolation tests caught real defects screenshots alone would miss (RLS write-side, audit immutability, the include_router version break).
- **Opus reviews on cx:high**: caught a silent-skip CI gap, forgeable audit rows, a TRUNCATE bypass, and an async event-loop stall — all before merge.

## What bloated
- Gemini transport debugging (AQ.-key needs header auth + v1beta + gemini-2.5-flash) cost a detour; now documented.
- Two silent seed failures (PGRST102 uniform-keys) — fixed by making seeds fail loudly.

## One mistake made
- `uv sync` silently upgraded fastapi/starlette into a version where `include_router` mounts routes as `path=None`, breaking all engine routes. Caught by a route-count check; fixed by pinning. Lesson: pin web-framework versions in a long build.

## One pattern to reuse (→ promoted to skill? n)
- Concurrent model calls (`ThreadPoolExecutor`) for per-item AI work (extract/analyze/draft) — sequential blows the request budget. Applied to drafter, analyzer.

## Pitfalls appended to known-pitfalls.md
- include_router version break; PGRST102 uniform-keys; AQ.-key transport.

## Karpathy rule broken
- None flagrant; a few screens (S6/S8/S12) were delegated read-mostly and skip the full reference chrome (flagged in-code).
