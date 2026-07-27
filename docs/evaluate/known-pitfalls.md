# Known pitfalls — Evaluate

Read before writing code; append when you hit a new one. Format: **symptom → cause → fix.**

The bidder-side list (`../known-pitfalls.md`) applies to shared technology — Next.js hydration,
Supabase RLS, container paths, latency. **Everything below is specific to this product**, and
most of it is seeded from PRD §6.2 before the bugs exist rather than after.

## The wall

- A guard that cannot fail is worse than no guard, because it is believed → `tools/check-wall.sh`
  v1 excluded matches whose path started with the evaluate app dir, which was every file it was
  meant to inspect; it reported "wall: intact" on a planted cross-import → name the evaluate
  package `evaluate/`, and **plant a breach and watch it go red** before trusting any green.
- The realistic wall breach is not malice, it is a refactor extracting a "shared" `db.py` → no
  shared data-access module, by rule.
- Convergent config — someone points staging at the bidder database "just to test" → F13-AC2
  compares the hosts and fails the build if they are equal.

## The sealed-bid gate

- The gate enforced in the page but not the API, the export, or an error branch that returns
  partial data → test it at the API layer; `tests/test_sealed_bid_gate.py` is required by CI.
- A financial figure leaking through the RSC payload while the UI correctly hides it → assert
  absence from the **network response**, not just the DOM.
- Technical reopened after financials were seen — the bell cannot be un-rung → re-seal, and the
  prior opening stays in the audit trail permanently (F9-ERR3).

## Scoring

- The AI proposal leaking into a prefetch or the RSC payload though the UI hides it → F7-AC3
  asserts the network response.
- Anchoring: evaluators overwhelmingly accept a pre-filled number, which makes the model the de
  facto decider while the audit trail claims human authorship → blind-first reveal, plus a
  per-evaluator deference rate in the audit pack. "Accepted unchanged in 47/47" is the signal.
- A consensus mark silently overwriting the individual marks that justified it → `consensus_marks`
  is a separate table; `scores` rows are never mutated.
- The mean quietly standing on a criterion nobody discussed → a variance-flagged criterion has
  **no** committee mark until consensus is recorded.
- Removing an absent member to "reach quorum" → removal does not lower the quorum. This is the
  first rule a losing bidder's lawyer checks.

## Screening

- "Absent from the bid" silently treated as "fails the criterion" — which disqualifies a bidder
  on an extraction miss → `Not stated` is its own verdict requiring human resolution.
- Comparators drifting into prompts, so the model decides responsiveness → `evaluate/deterministic/`
  only, import check in CI.

## Ranking

- Floating-point drift making two equal bids rank arbitrarily → decimal arithmetic; exact ties
  render as ties.
- Software applying an unpublished tie-break rule and inventing a winner → ranking cannot
  finalise until a human records the rule and the outcome. This is what gets an award set aside.

## Records

- An UPDATE grant on `audit_events` added by a later migration → grant revoked at DB level and
  asserted against the service role.
- Append-only meets a deletion request → it cannot be honoured in-product; the bidder side proved
  the trigger refuses even the service role. Erasure is a documented process with a named
  approver, not a feature. Do not "fix" this by weakening the trigger.

## Ingestion (found by running it, 2026-07-27)

- A lazily-imported dependency that is not in `pyproject.toml` fails at RUNTIME, not at import,
  not in tests, and not in lint → `pypdf` was missing for the whole build of the upload feature
  and only surfaced when a PDF was actually parsed. If you add `from x import y` inside a
  function, add x to the dependencies in the same commit.
- **Money units are the most dangerous field in this product.** An RFP says "Rs. 5 Crore" and a
  bid says "Rs. 12.40 Crore"; if one extraction yields 50000000 and the other 12.4, the
  comparison silently fails a qualifying bidder and nothing looks wrong. Both prompts state
  WHOLE RUPEES explicitly. If you touch either prompt, re-run the two-bidder fixture and check
  the turnover row.
- `present` as a comparison operator is permissive by definition — it asks only whether a value
  exists. A live extraction chose it for "certificate valid as on 20/07/2026", which would have
  **passed a certificate that expired five months earlier**. `pipeline/extractor.py` now coerces
  `present` to `>=` on numeric/date criteria, one-directionally: never coerce the other way,
  because that direction lets a failing bidder through. `test_screening.py` records what the
  bug costs so nobody removes the coercion casually.
- `present` also reached `screening._cmp`, which only understood `>=`, `<=` and `=`, and raised
  `ValueError` → a 500 on any tender saying "shall furnish". Handled explicitly before the
  comparison now.
- Extraction pulls the qualifying threshold and the QCBS weighting out of the evaluation section
  as if they were criteria. They describe how criteria are USED; as criteria they make every
  bidder read "Not stated". The prompt now excludes them by name.
- The model echoes the label with the clause number ("Cl. 3.1(a)"), and the UI adds its own
  label → "Cl. Cl. 3.1(a)". Normalise at ingest so one convention reaches the database, rather
  than papering over it in each component that renders an anchor.
- A tender cannot be deleted once anything is audited — `audit_events` is append-only and the
  cascade is refused even to the service role. `state='archived'` plus a `neq.archived` filter
  in `db.tenders()` is the only removal this product has, and that is deliberate.
