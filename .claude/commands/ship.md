---
description: Pre-deploy gate. Runs the production-readiness audit; blocks on missing evidence.
---

Delegate to the **production-readiness** subagent for the full gate.

Preconditions it will enforce (stale or missing evidence = finding, not pass): all gate ACs green at their tagged layers, latest /verify, /verify-api, /evals, /design-review results, secrets scan clean, `.env.example` complete, tenant-isolation tests green.

Paste the findings table + verdict verbatim. `BLOCK` or `SHIP WITH FIXES` → resolve the list and re-run /ship. Only `SHIP` means ship.
