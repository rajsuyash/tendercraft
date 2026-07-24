---
description: Plan the current milestone into an executable task list. Never starts coding.
argument-hint: [milestone id, e.g. M1 — defaults to first milestone with unmet exit criteria]
---

Read `docs/PRD.md` §5 (build sequence M0–M5). Target milestone: $ARGUMENTS if given, else the first whose exit criteria are not yet passing.

1. Load ONLY that milestone's scope (plus §0 contract, §4 decisions, PRD non-goals) and the relevant module spec from `tendercraft-PRD.md`
2. Decompose into ordered tasks; each task names the AC IDs it will satisfy and its verification layer (unit / integration / browser-verify / design-review / evals)
3. UI tasks get their `design_ref` (S-id from docs/DESIGN_SPEC.md §D) attached — the task is not plannable without it
4. Order vertically: each task leaves the app runnable and demoable; schema-only or UI-only task chains are wrong
5. Tag complexity (low/med/high). High (tenant isolation, gates, audit, comparators): plan the approach in one paragraph before any code, schedule `/review` before done. Tasks with design_ref floor at med.
6. Flag blockers: `TODO:` markers (OCR provider!), missing fixtures (§10), missing env vars, human-only tasks (Supabase project creation, deploy accounts)

Output: the task table (id, task, ACs, design_ref, verify layer, complexity), blockers list, and the milestone's demoable check restated. STOP after the plan — do not begin implementation in this invocation.
