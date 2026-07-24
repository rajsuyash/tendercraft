# Eligibility-matcher evals

Run: `cd services/engine && uv run python -m evals.run eligibility-matcher`

## Thresholds (from tendercraft-PRD.md Module C — full gold set, not starters)

| Metric | Threshold | AC |
|---|---|---|
| Sub-0.75-confidence routed to needs_review (never auto-pass) | 100% | C-AC5 |
| Pass with empty evidence | 0 (schema-invalid) | §5.1 |
| Eligibility accuracy vs evaluator outcomes | ≥ 85% | C-AC1 (outcome-matched, post-launch) |
| False-positive rate | < 5% | C-AC2 / ET-1 |
| Gap-detection completeness | ≥ 90% | C-AC3 |

## Status

Starters prove the harness + the conservative-default behavior. C-AC1/2 need the outcome corpus (PRD §6) — they are production monitors, not offline starters. Never edit cases to make a run pass.
