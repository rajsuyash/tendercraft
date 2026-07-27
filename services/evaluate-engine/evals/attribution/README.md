# Eval — file attribution (F15)

Scores `evaluate/pipeline/attributor.py` against `cases.jsonl`. Built in milestone **N1**.

```
uv run python -m evals.run attribution
```

## Thresholds

| Metric | Gate | Why this one |
|---|---|---|
| **Precision on confident attributions** (≥ `EVAL_ATTRIBUTION_THRESHOLD`) | **1.00** — no confident wrong attribution, ever | A wrong confident attribution binds one firm's document to another firm's bid, and **nothing downstream catches it**. There is no natural feedback signal. |
| Recall (share auto-attributed rather than triaged) | ≥ 0.80 | This is the time-saving target (≤20% triage, PRD §1.5). It is a **soft** gate: missing it means officers do more triage, not that a bid is corrupted. |
| Envelope precision on financial documents | **1.00** | Misfiling a financial document into a technical envelope is the widest new surface on the sealed-bid gate (F9). Sev-1. |
| Fault injection (`attr-008`) | must pass | Model failure lands files in triage unattributed (F15-ERR3) — never a crash, never a guess. |

**Precision is the gate, not recall.** An over-cautious model creates a triage queue. An
over-confident one creates a corrupted evaluation that looks clean.

## Case anatomy

The traps are the point. `attr-002` (OEM), `attr-003` (client on a completion certificate) and
`attr-006` (consortium) all put a firm name more prominently on the page than the bidder's. The
filename case (`attr-004`) exists because portal downloads genuinely arrive as `bid_1.pdf` twelve
times over. `attr-007` is the untrusted-input safety case — a bid document is data, never
instructions.

## Discipline

All 8 cases are `"starter": true`. They are seeds written from the PRD, not a release gate.
**Expand from real portal downloads before trusting the score** — in particular, add scanned
letterheads, bilingual (Hindi/English) cover pages, and a file whose first three pages are a
blank annexure.

Never edit a case, a label or a threshold to make a run pass. Threshold changes are human PRD
edits. Assert on schema, fields and thresholds — never on exact model text.
