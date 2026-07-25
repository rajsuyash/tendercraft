# Drafter evals

Run: `cd services/engine && uv run python -m evals.run drafter`

Guards the cite-or-flag behaviour (Module B) with live Gemini. The central property this set
protects: **a financial/numeric requirement backed by evidence drafts a compliant, cited response
WITHOUT the model authoring a figure** — so it is not hard-flagged `uncited_financial` (B-AC4).

## Thresholds (release gates from tendercraft-PRD.md §4 Module B — apply to the FULL gold set)

| Metric | Threshold | AC |
|---|---|---|
| No model-authored financial figure (`uncited_financial` flag) on evidence-backed drafts | 100% | B-AC4 / B-FR3 |
| Citation validity (fact sentences resolve to a chunk) | ≥ 95% | B-AC3 |
| Placeholder on genuinely-unsupported criteria (no invention) | 100% | B-FR2 / G-5 |
| Fault injection (model error → placeholder, never crash/invention) | 100% | §5.1 |
| Regression guard | > 2-point drop on gold set blocks the change | §5.3 |

## Cases

- `drf-001` financial turnover + CA cert → drafted, cited, **no** `uncited_financial` (the B-AC4 case)
- `drf-002` non-blacklisting undertaking → drafted, cited
- `drf-003` ISO-27001 asked, only a turnover cert present → placeholder (no hallucinated cert)
- `drf-004` three software works + completion certs → drafted, cited (counts not authored)
- `drf-inj-1` injected model error → placeholder fallback

## Status

Cases marked `"starter": true` prove the harness + the B-AC4/B-FR3 property, not release-grade
quality. The real gold set is the PRD §6 drafting corpus. Never edit a case or threshold to make a
run pass — threshold changes are human PRD edits (§5.3).
