# Extractor evals

Run: `cd services/engine && uv run python -m evals.run extractor`

## Thresholds (release gates from tendercraft-PRD.md §4 Module A — apply to the FULL gold set, not starters)

| Metric | Threshold | AC |
|---|---|---|
| Criterion recall | ≥ 95% | A-AC1 |
| Criterion precision | ≥ 90% | A-AC1 |
| Requirement-level classification F1 | ≥ 0.90 | A-AC2 |
| Source-anchor resolvability | 100% | A-AC3 |
| Schema validity | 100% (retry-once then queue) | §5.1 |
| Regression guard | > 2-point drop on gold set blocks the change | §5.3 |

## Status

Cases marked `"starter": true` prove the harness only. The real gold set is the PRD §6 annotation corpus (≥500 tenders, ≥100 for A-AC1's gate). Expand before treating scores as release gates. Never edit cases to make a run pass.
