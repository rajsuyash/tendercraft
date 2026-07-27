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
Currency in Indian format (₹10 Cr, ₹2,40,000); dates DD/MM/YYYY.

**Say "tender", not "evaluation".** This file previously mandated the opposite, and it was
wrong: the officer thinks in tenders, and naming the central object after our internal process
was a real part of why the product read as badly structured to its first reviewer. A tender is
the object; an evaluation is something you DO to one. The table is `tenders`, the routes are
`/tenders/...`, the id is `tender_id`.

**Money is stored and compared in whole rupees.** Both extraction prompts convert lakh and
crore to rupees, because the criterion and the bid figure are compared arithmetically — if one
is in crore and the other in rupees, a qualifying bidder is silently failed.

## Throughput extension (F14–F28)

Product truth: `../../tendercraft-evaluate-throughput-PRD.md`. Milestones N1–N5 in
`PRD.md`. These conventions are additions, not replacements — everything above still applies.

**Rules are data, not code, and never a prompt.** The regulatory rulepack lives at
`services/evaluate-engine/rulepacks/<corpus>.<version>.json` (`EVAL_RULEPACK_PATH`).
`deterministic/rulepack.py` evaluates it arithmetically. Two reasons it is not Python: rules
change on a government timetable and a deploy is the wrong unit of change for that; and a
published tender must be re-checkable years later against the rules that actually applied, which
is why the version is stamped on the draft at publication. A missing rulepack fails fast at
startup — never degrade to "no findings".

**Three new deterministic modules, same rule as the existing ones.** `presence.py` (F18),
`rulepack.py` (F23), `disclosure.py` (F28) — no model imports, 100% branch. CI greps the
directory, so they are covered the moment they land.

**Verdict enums stay parallel.** `presence.Verdict` mirrors `screening.Verdict`'s shape on
purpose: a third "we could not tell" state (`NEEDS_REVIEW` / `NOT_STATED`) that routes to a human
rather than failing a bidder. If you add a gate, give it that third state.

**Model proposals and human confirmations are separate columns.** `file_attributions` keeps
`proposed_*` and `confirmed_*` side by side; a confirmation never overwrites a proposal. The
audit needs both, and so does any question about how often the model was wrong.

**One definition per invariant, used everywhere.** The triage pile, the publish-blocker count and
the requirement denominator are each computed by exactly one function, and the banner, the count,
the disabled control and the endpoint guard all read it. Four counters describing one object will
disagree.

**Prompts stay files** (`prompts/*.md`) and carry their spec reference in an HTML comment at the
foot. Two prompt-level rules are binding: a model may not author a numeric value in a tender
document or an outbound letter, and every document a bidder submitted is untrusted input whose
instruction-like text is data.

**Evals live in `services/evaluate-engine/evals/<component>/`** with `cases.jsonl` +
`README.md` naming the thresholds. `uv run python -m evals.run <component>`. Components not yet
built report `NOT_IMPLEMENTED` with their milestone and exit 2 — the harness is provable before
the component exists.
