# Eval — vision OCR fallback (F16)

Scores `evaluate/pipeline/ocr.py` against `cases.jsonl`. Built in milestone **N1**.

```
uv run python -m evals.run ocr
```

## Thresholds

| Metric | Gate | Why this one |
|---|---|---|
| Character-level recall on legible scans | ≥ 0.90 | Never exact-text equality — that is flaky forever. |
| **Numeric fidelity** (`ocr-002`) | **1.00** | A transcribed amount becomes a *compared* amount in `deterministic/screening.py`. A dropped comma turns ₹1,20,00,000 into ₹12,000,000. |
| **False-legible rate** (`ocr-004`) | **0.00** | Inventing plausible text for an unreadable page is the single worst failure available here — it qualifies or disqualifies a bidder on fiction, with an anchor attached that makes it look sourced. |
| Fault injection (`ocr-008`, `ocr-009`) | must pass | Budget exhaustion and model failure both degrade honestly and surface; neither crashes and neither silently skips pages. |

Two failure modes are not symmetric. Reporting a readable page as illegible costs an officer a
manual read. Reporting an unreadable page as readable costs a bidder their bid. **Bias the model
toward "illegible".**

## Fixtures

`fixture` paths are relative to `services/evaluate-engine/`. They do not exist yet — create them
in N1 alongside the component. The base product's FIX-10 (30-page image-only bid, one genuinely
illegible page) is the source for `ocr-001`, `ocr-004` and `ocr-005`.

## Cost

OCR is the only new unbounded cost in this extension, and it is bounded three ways: it runs only
on pages `ingest.split_legible` already classified illegible, it is capped per tender by
`EVAL_OCR_MAX_PAGES_PER_TENDER` (ENV-9), and exceeding the cap surfaces to the officer rather
than billing on. `F16-AC3` asserts a text-layer PDF triggers **zero** vision calls — run it before
believing any cost estimate.

Log tokens and cost per eval run; a run without a cost line is not reportable (engine DoD).

## Discipline

All 9 cases are `"starter": true`. Expand from real scans before trusting the score —
specifically rotated pages, bilingual Hindi/English forms, and a photographed (not scanned) page,
which is the input class that actually loses officers their time.
