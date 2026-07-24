---
description: Verify engine behavior — integration tests for affected endpoints plus live smoke of documented routes.
argument-hint: [endpoint path, module (A/B/C/D/E), or "all"]
---

Scope: $ARGUMENTS, else endpoints touched by the current diff mapped through `docs/PRD.md` §6.

1. Run the integration suite scoped to affected endpoints (`cd services/engine && uv run pytest -k <filter>`)
2. If the engine runs locally (http://localhost:8000): curl each in-scope endpoint — happy case + one documented error case each; assert status AND the `{ ok, data, error }` envelope shape
3. Confirm error paths return the envelope with a stable `code`, not stack traces
4. Endpoints touching tenant data: assert a body-supplied `tenant_id` is ignored (session wins — ET-6)

Output a table: endpoint | case | expected (status+shape) | got | verdict. Then `SUMMARY: n PASS / n FAIL`. FAIL → fix and re-run before claiming done.
