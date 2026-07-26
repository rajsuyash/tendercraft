---
description: Integration + live smoke verification for the EVALUATE engine (services/evaluate-engine).
argument-hint: [endpoint, feature (F9), or "all"]
---

Verify `services/evaluate-engine` against the contracts in `tendercraft-evaluate-PRD.md` §6.1.

Scope: $ARGUMENTS if given; otherwise the endpoints touched by the current diff.

Run, in order:
1. `cd services/evaluate-engine && uv run ruff check`
2. `uv run pytest tests --ignore=tests/isolation -q`
3. Deterministic gates at 100% branch: `uv run pytest tests --ignore=tests/isolation -q --cov=evaluate/deterministic --cov-branch --cov-fail-under=100`
4. `uv run pytest tests/isolation -q -rs` — authority A must never see authority B (FIX-8). A **skipped** isolation test is not a passing one; report skips as failures.
5. `./tools/check-wall.sh` — F13. Must exit 0.
6. Live smoke of the affected endpoints against http://localhost:8001 (BLOCKED if down — do not start it).

**Gate assertions that must be checked at the API layer, never through the UI** — the requirement is that the data is unreachable, not that a button is hidden:
- `GET /api/evaluations/:id/financial` → `409 FINANCIAL_SEALED` before technical lock, and the body contains no amount (F9-AC1)
- `POST .../technical/lock` → `409 QUORUM_NOT_MET` below quorum, `409 CONSENSUS_REQUIRED` with unresolved variance (F8-AC1/AC5)
- `GET .../scores/:bidId/proposal` → `409 OWN_MARK_REQUIRED` before the evaluator's own mark exists (F7-AC3)
- `POST .../framework/lock` then any framework mutation → `409 FRAMEWORK_LOCKED` (F3-AC2)
- Any write as an `auditor` → 403 (F1-AC3)

Report a table: endpoint · method · expected status · actual · PASS/FAIL. Every error path must return the `{ok,data,error}` envelope, never a stack trace. Any FAIL → fix and re-run before claiming done.
