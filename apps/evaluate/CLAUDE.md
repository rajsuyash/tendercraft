# apps/evaluate — TenderCraft Evaluate (web)

**This is the GOVERNMENT-side product.** Officers and technical evaluation committees scoring
submitted bids. It is not the bidder app. If you are reading this you are in the evaluate
subtree and the rules below override the root `CLAUDE.md` where they differ.

- Product truth: `../../tendercraft-evaluate-PRD.md` · execution layer: `../../docs/evaluate/PRD.md`
- Conventions: `../../docs/evaluate/conventions.md` · pitfalls: `../../docs/evaluate/known-pitfalls.md`

## The wall (F13) — read this before anything else

This repo contains a product that helps bidders **win** tenders (`apps/web`) and a product that
**scores** those tenders for the buyer (here). They share design tokens and CI patterns. They
share no data, no database, no credential, and no line of data-access code.

- **Never import from `apps/web` or `services/engine`.** Not "prefer not to" — never. Copy instead.
- `NEXT_PUBLIC_EVAL_SUPABASE_URL` must never equal `NEXT_PUBLIC_SUPABASE_URL`.
- `./tools/check-wall.sh` enforces this in CI on every push. If you change it, plant a breach and
  watch it fail before you trust it passing.

## Non-negotiable

1. **AI reads and writes; code decides.** No model output determines responsiveness,
   qualification, a mark, a rank, or whether an envelope may open.
2. **Sealed bids.** Reaching financial data before technical lock — by API, export, prefetch,
   RSC payload, or an error branch — is Sev-1. Assert against the *network response*, not the DOM.
3. **Blind-first scoring.** The AI-proposed mark must be absent from the DOM and every network
   response until the evaluator's own mark is recorded (F7-AC3).
4. **Every mark belongs to a named human.** No system-authored score exists anywhere.
5. Authority id derives from the session, never a request body.
6. Design tokens only — no hardcoded hexes or font stacks.
7. Every route group has a `loading.tsx`; layout data sits behind `<Suspense>`; independent reads
   use `Promise.all`. The bidder app shipped without these and every click froze for seconds.

## Commands

```
pnpm dev:evaluate         # :3001 → pipe to a log: pnpm dev:evaluate 2>&1 | tee .claude/evaluate-dev.log
pnpm build:evaluate
pnpm typecheck:evaluate
pnpm lint:evaluate
pnpm test:evaluate
pnpm seed:evaluate        # idempotent; tenants A (empty) / B (seeded) / C (isolation)
```

## Definition of done

1. `pnpm typecheck:evaluate` and `pnpm lint:evaluate` exit 0
2. `pnpm test:evaluate` passes
3. `./tools/check-wall.sh` exits 0
4. `/verify-eval` run on every affected route — zero console errors, zero unexpected 4xx/5xx,
   screenshot attached. Authenticated routes sign in as FIX-1.
5. Journey ACs run against **tenant A (empty)** — a J-AC on a seeded account tests nothing
   about first run
6. One-line summary naming the AC IDs satisfied
