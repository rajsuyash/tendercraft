# TenderCraft Evaluate — conventions

Inherits the bidder-side conventions (`../conventions.md`) for anything not restated here.
Where they differ, this file wins for `apps/evaluate` and `services/evaluate-engine`.

## The three rules that are specific to this product

1. **The engine package is `evaluate/`, never `app/`.** See `architecture.md` for why — it is
   what makes the wall check unambiguous.
2. **No import, ever, from `app/`, `pipeline/`, or `apps/web`.** Not "avoid" — none. If you need
   something the bidder engine has, copy it. Duplication is the cheaper failure here.
3. **A model may never return a value that a gate reads.** The score-proposer proposes to a
   human; it does not write `final_mark`.

## Next.js (`apps/evaluate`)

- Server Components by default; `"use client"` at the leaf only.
- Mutations go through route handlers (thin BFF) that validate with zod and forward to the engine.
- **Every route group gets a `loading.tsx`.** The bidder side shipped without one and every
  navigation was a frozen screen until the whole server render finished — 6.8s on the worst page.
  Do not repeat it.
- Layout-level data must sit behind `<Suspense>`. Data fetched in a layout is re-fetched on every
  navigation and blocks first paint for all of them.
- Independent reads use `Promise.all`. Two consecutive `await`s with no data dependency is the tell.
- Design tokens (`design/tokens.json`) are the only source of colour/type/spacing — shared with
  the bidder app deliberately, because tokens carry no data.

## FastAPI (`services/evaluate-engine`)

- Response envelope: `{ ok, data, error: { code, message } }` on every path including errors.
  Stack traces are logged, never returned.
- Error codes are stable `SCREAMING_SNAKE` strings — the UI switches on `code`, never on message
  text. The gate codes are load-bearing: `FINANCIAL_SEALED`, `QUORUM_NOT_MET`,
  `CONSENSUS_REQUIRED`, `FRAMEWORK_LOCKED`, `OWN_MARK_REQUIRED`, `TIE_UNRESOLVED`.
- Authority id comes from the verified JWT. Never from a request body. This is authz bug class #1
  and the bidder side already shipped a Sev-1 on it.
- **One pooled `httpx.Client`** with `keepalive_expiry` set explicitly. The bidder side learned
  this twice: module-level `httpx.get()` opens a new TLS connection per query, and the library's
  5-second default keepalive means pooling helps *within* a request and not between them.
- `evaluate/deterministic/` is pure functions over typed inputs. No model imports — CI enforces it.

## Prompts and evals

- Prompts are files in `services/evaluate-engine/prompts/`, never string literals.
- **Never seed a golden case from bidder-side data.** The wall check greps for it (F13-AC3).
- Every model output is schema-validated before use: validate → one retry → deterministic
  fallback. For the score-proposer the fallback is *no proposal*, never a guessed mark.

## Naming

`camelCase` TS · `snake_case` Python · `PascalCase` components · `UPPER_SNAKE` constants.
Currency in Indian format (₹10 Cr, ₹2,40,000); dates DD/MM/YYYY. Use "evaluation", never
"project" or "tender" — a tender is the thing being evaluated, an evaluation is our object.
