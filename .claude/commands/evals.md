---
description: Run golden-set evals for AI pipeline components and enforce PRD thresholds.
argument-hint: [component (extractor | eligibility-matcher) — defaults to components whose prompts/ or pipeline code changed]
---

Delegate to the **eval-runner** subagent. Scope: $ARGUMENTS, else every component whose `services/engine/prompts/`, `evals/`, or `pipeline/` code appears in the current diff.

Paste the subagent's metric table (threshold vs measured) + SUMMARY verbatim. Any threshold miss → this change is NOT done; fix the prompt/code (never the golden set) and re-run. Include the cost/token log line for the run.
