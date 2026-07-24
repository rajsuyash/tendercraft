# Eligibility Matcher — fuzzy criterion vs vendor profile

Spec: tendercraft-PRD.md §5.1 (Eligibility matcher row), Module C (C-FR2).

## Contract (binding)

- Input: one fuzzy criterion (e.g. "three similar works of comparable nature") + candidate experience records
- Output: tool-use JSON — `{verdict: pass|fail|needs_review, evidence: [record_ids], rationale, confidence: 0..1}`
- Confidence < 0.75 → verdict forced to `needs_review` by the deterministic router (C-AC5) — the model's verdict is advisory below threshold.
- Cannot emit `pass` with empty evidence — schema-enforced.
- Numeric/date/boolean comparisons are NOT this component's job (deterministic comparators own them, PRD §2.4).

## Prompt

TODO: author at M2. Structure: role, "similar nature of work" interpretation guidance (scope tags, client type, value bands), conservative-default instruction (ET-1: when in doubt, needs_review), rationale citing specific records, few-shots from FIX-2 profile vs FIX-3 criteria.
