# Analyzer evals — reading an eligibility requirement

Run: `cd services/engine && uv run python -m evals.run analyzer`

## What replaced what, and why the old cases are not here

This directory supersedes `evals/eligibility-matcher/`, which was retired in the same commit
along with `prompts/eligibility-matcher.md`. That is a deletion of a golden set, so it needs
a reason on the record.

The matcher's contract was `{verdict, evidence, rationale, confidence}` — **the model
returning a verdict**, with a deterministic router downgrading it below 0.75. Its five cases
were all assertions about which verdict the model should reach. That component no longer
exists: the model now describes what the tender DEMANDS and `app/deterministic/facts.py`
decides, so there is no model verdict left to score. Its prompt was never authored (it read
`TODO: author at M2`), nothing imported it, and `eligibility-matcher` was absent from
`COMPONENTS` in `evals/run.py`, so the runner refused the name — five golden cases that
nothing could run.

The cases were not edited to make a run pass. They were scoring a component that was removed.

## Thresholds

| Metric | Threshold | AC |
|---|---|---|
| Every case reads the correct `check` | 100% | C-AC5 |
| Money thresholds converted exactly (Lakh vs Crore) | 100% | C-FR1 |
| A relative window stays a COUNT, never invented years | 100% | C-FR1 |
| A post-award duty / instruction / blank form reads as `none` | 100% | §2.4 |
| No verdict field is populated, ever | 100% (structural) | §2.4 |
| Model failure → `none` at confidence 0.0 | 100% | ET-1 / G-5 |
| Eligibility accuracy vs evaluator outcomes | ≥ 85% | C-AC1 (outcome-matched, post-launch) |
| False-positive rate | < 5% | C-AC2 / ET-1 |

C-AC1 and C-AC2 need the outcome corpus (PRD §6) — they are production monitors, not offline
starters, and that was true of the retired set too.

## What these cases cannot tell you

**Confidence is not a constant, and it is also not a calibrated instrument.** Measured
2026-09-15 against Gemini 2.5 Flash: ten of the ten golden criteria came back at 0.90–1.00,
and a bare `"Rs. 10 Cr"` with no surrounding sentence came back at 0.10. So the 0.75 guard in
`decide_requirement` does fire, but only on input that is obviously fragmentary — it is not
load-bearing against a confident misreading of a real clause. The protection against that is
structural rather than statistical: the model cannot see the bidder, the enum is the
allowlist, and a stated threshold the profile cannot answer is needs-review however sure the
model was. Do not tighten the threshold expecting it to catch more; measure first.

Never edit a case or a threshold to make a run pass — threshold changes are human PRD edits.
