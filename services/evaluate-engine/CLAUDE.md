# services/evaluate-engine — TenderCraft Evaluate (engine)

**Government-side evaluation engine.** Not the bidder engine. Rules here override the root
`CLAUDE.md` where they differ.

- Product truth: `../../tendercraft-evaluate-PRD.md` · execution layer: `../../docs/evaluate/PRD.md`
- Conventions: `../../docs/evaluate/conventions.md` · pitfalls: `../../docs/evaluate/known-pitfalls.md`

## The wall (F13)

**The Python package here is `evaluate/`, never `app/`.** The bidder engine's package is `app/`,
so inside this tree `from app…` or `from pipeline…` can only mean a cross-product import — which
is what makes `tools/check-wall.sh` able to catch it. Naming this package `app/` re-creates the
ambiguity that let the first version of that check pass on a planted breach.

Never import `app`, `pipeline`, or anything under `apps/web`. Copy instead. `./tools/check-wall.sh`
runs in CI on every push.

## Non-negotiable

1. `evaluate/deterministic/` decides; `evaluate/pipeline/` reads and drafts. **No model imports
   in `deterministic/`** — CI greps for them. 100% branch coverage, `--cov-fail-under=100`.
2. **The sealed-bid gate is the product.** `GET /api/evaluations/:id/financial` returns
   `409 FINANCIAL_SEALED` until technical lock. Enforce it in the RLS policy AND the handler AND
   an integration test. `tests/test_sealed_bid_gate.py` is required by CI.
3. Envelope `{ ok, data, error: { code, message } }` on every path including errors. Stack traces
   are logged, never returned.
4. Authority id from the verified JWT. Never from the body.
5. **One pooled `httpx.Client` with an explicit `keepalive_expiry`.** Module-level `httpx.get()`
   opens a fresh TLS connection per query; the 5-second library default means pooling helps
   within a request and not between them. The bidder side paid for both lessons.
6. The score-proposer's fallback is **no proposal**, never a guessed mark.

## Commands

```
uv run fastapi dev evaluate/main.py     # :8001
uv run pytest                            # unit + integration
uv run pytest tests/isolation -q         # authority isolation, CI-blocking
uv run ruff check
uv run python -m evals.run <feature>
```

## Definition of done

1. `uv run ruff check` and `uv run pytest` exit 0
2. Deterministic gates at 100% branch
3. `./tools/check-wall.sh` exits 0
4. `/verify-eval-api` passes — endpoints listed with tested statuses; error paths return the
   envelope, not a stack trace
5. Prompt or eval changes → `/evals` run, thresholds met, no golden case edited to pass
6. One-line summary naming the AC IDs satisfied
