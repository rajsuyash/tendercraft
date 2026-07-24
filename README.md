# TenderCraft

AI-native platform for Indian tender compliance: tender PDF → verified criteria model (TOM) → pre-bid eligibility verdicts → cited, compliant proposal drafts. Humans approve everything that leaves the system.

## Prerequisites

- Node 20+ · pnpm 9+
- Python 3.12 · [uv](https://docs.astral.sh/uv/)
- Supabase project (URL + keys in `.env` — see `.env.example`)
- Anthropic API key

## Setup

```bash
cp .env.example .env            # fill values
pnpm install                    # web deps (apps/web)
cd services/engine && uv sync   # engine deps
```

## Run

```bash
pnpm dev 2>&1 | tee .claude/dev-server.log     # web → http://localhost:3000
cd services/engine && uv run fastapi dev app/main.py   # engine → http://localhost:8000
pnpm seed                                       # reset fixtures (FIX-1..5)
```

## Test / verify

```bash
pnpm typecheck && pnpm lint && pnpm test        # web
cd services/engine && uv run pytest             # engine
cd services/engine && uv run python -m evals.run extractor   # golden-set evals
```

## Docs

- `tendercraft-PRD.md` — product PRD (source of truth, never agent-edited)
- `docs/PRD.md` — execution layer: milestones, routes, env, fixtures
- `docs/DESIGN_SPEC.md` + `design/` — approved design contract (13 screens, tokens, reference renders)
- `docs/architecture.md` · `docs/conventions.md` · `docs/test-strategy.md` · `docs/known-pitfalls.md`

Built with Claude Code: start sessions with `/plan M0`.
