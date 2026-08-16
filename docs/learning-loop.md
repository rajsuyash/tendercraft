# The self-learning knowledge base — architecture decision

**Status:** **built 2026-08-16 (Phases 1–4)** · proposed 2026-08-15 · **Prompted by:** owner
request — *"the system should keep learning from each tender filled by the client so that after
5-6 tenders the knowledge base becomes self-sufficient"*
**Decision owner:** human sign-off required before Phase 5

> **Built, and what to ratify.** Phases 1–4 shipped on 2026-08-16. Two divergences to ratify,
> per CLAUDE.md's rule that reality contradicting the spec is proposed, not silently drifted:
>
> - **S21 `/knowledge` is a new screen id** not in `docs/DESIGN_SPEC.md` §D. S19/S20 were
>   already taken by the Module H capability and schedule-fit screens
>   (`docs/feedback/usha-martin.md`), which are themselves awaiting ratification.
> - **`GET /api/learning/maturity` is a new route** not in `docs/PRD.md` §6. It lives in
>   `app/reuse_routes.py` rather than a new router: it measures the answer library, which that
>   file already owns, and a second router for one read-only endpoint is a file nobody needs.
>
> One design decision changed during the build, and it is the important one. The plan said a
> harvested proposal becomes a `library_documents` row like an uploaded bid. **It must not.**
> That row would (a) let the retriever cite our own unverified draft as evidence — circular
> grounding that cite-or-flag would report as satisfied — and (b) enter `get_past_bid_texts`,
> which measures house style, converging the style brief onto the drafter's own voice. A
> harvest writes a `past_bids` row and answers, and nothing else. Style learns from human
> edits instead (Phase 2), which is the signal that means something anyway.

Follows the house shape for *an idea that changes the architecture* (`docs/multi-market.md`,
`docs/feedback/usha-martin.md`).

## Decision

**The learning layer already exists. It is not wired to the moments where learning happens.**

The instinct on hearing "self-learning knowledge base" is a vector store, embeddings, and a
fine-tune per client. That would be building a second copy of something this repo already
has — and it would be the wrong second copy, because the hard part here was never retrieval.
The hard part is *which text is worth keeping*, and that question is answered by a human
approving a section, not by a cosine distance.

So: **no new subsystem. Close four open loops in the one that exists.**

## What is already built

Measured by reading the code on 2026-08-15, not estimated.

| Piece | Where | What it does |
|---|---|---|
| `past_bids` / `answers` / `answer_usages` | migration `0027_answer_library.sql` | requirement → the answer that satisfied it, with outcome and an acceptance receipt |
| Deterministic mining | `deterministic/answer_mining.py` | headings and compliance-table rows → (requirement, answer) pairs, no model call |
| Model mining for the residue | `pipeline/answer_miner.py` | prose that answers a requirement it never names; `appears_verbatim` drops any paraphrase |
| Suggestion ranking | `deterministic/answer_reuse.py::rank_answers` | asymmetric lexical similarity, outcome-weighted, section-scoped |
| Staleness detection | `deterministic/answer_reuse.py::stale_claims` | names the document and the date it expired |
| Measured house style | `deterministic/style.py`, migration `0028` | tone brief templated from counts — **no source text reaches a prompt** |
| Accept-only write path | `app/reuse_routes.py` | `POST /api/proposals/{id}/reuse` is the only endpoint that inserts reused text (G-AC6) |
| Per-criterion evidence | `pipeline/retrieval.py::select_evidence` | IDF-weighted chunk selection, pinned-doc honouring |

That is a knowledge base. It has one defect, and it is not a modelling defect:

**It only learns from documents the client uploads by hand, and only when they remember to.**

## The four open loops

### 1. A tender filled *in TenderCraft* never becomes knowledge

`POST /api/tenders/{id}/export` (`app/proposal_routes.py:418`) is the moment a proposal leaves
the building. It writes an audit row and `mark_exported`, and that is all. The document the
client just spent two weeks on — approved section by section, corrected by hand, gated by the
export blocker — is not mined, is not a `past_bids` row, and is invisible to the next tender.

The absurdity is exact: **if the client exported that same file and re-uploaded it through
`POST /api/past-bids`, it would be mined perfectly.** The ingestion path
(`past_bids_routes.py::_process`) already does everything needed. Nothing calls it from inside.

This is the whole feature, and it is a wiring job.

### 2. The richest signal in the product is destroyed on every save

`edit_section` (`proposal_routes.py:308`) overwrites `body_md` in place. The AI's original is
gone.

The difference between what the model wrote and what the human shipped is the most valuable
correction this product ever sees — it is a labelled example of *this specific client's*
standard, produced free, at the exact moment a bid manager cared enough to retype a paragraph.
Every one of them has been thrown away.

One nullable column recovers it.

### 3. Acceptance is recorded and never read

`answer_usages` exists, is written by the accept endpoint, and **nothing queries it.**
`rank_answers` weights by outcome and recency only. An answer a human has accepted four times
across four tenders ranks identically to one nobody has ever taken.

That table *is* the learning signal. It is already being collected.

### 4. Nothing collapses duplicates, so the base gets noisier as it grows

After six tenders there are six near-identical answers to "Understanding of the Project", one
per bid, all scoring within a few points of each other. The reuse panel shows three of them.
The user learns the panel is noise and stops reading it — which costs more than showing
nothing (a floor `answer_reuse.py` already sets for a different reason at `_MIN_SIMILARITY`).

**Growth must mean convergence, not accumulation.** Right now it means accumulation.

## Architecture

Four signals, one store, one ranker, two injection points. Everything workspace-scoped.

```
  SIGNAL                          STORE                  USE
  ──────────────────────────────  ─────────────────────  ────────────────────────
  export (approved sections)  ─┐
  human edit (original→final) ─┼─▶ answers            ─▶ rank_answers ─▶ reuse panel
  accept / ignore a suggestion ─┤   answer_usages          (suggest only,
  outcome won/lost (user-set) ─┘                            human accepts)
                                                        
  edit magnitude + shape      ───▶ style_profiles      ─▶ drafting prompts
                                   (counts only)           (tone/shape only)
```

Five rules the design is built around. Each is an existing product guarantee, not a new one.

**1. Only human-signed text is knowledge.** Mine a section if and only if it was `approved_by`
a person or `edited_by` a person. AI prose nobody signed off is the model's guess; mining it
teaches the system its own output, and after five tenders the client's knowledge base is a
compressed recording of the drafter's habits. That is model collapse, and it would arrive
disguised as exactly the success the feature promises — rising reuse coverage, falling edit
rates, and prose drifting steadily away from how the client writes. The approval gate that
already exists (`approve_section`, B-FR4) is the filter, and it is free.

**2. Suggest, never insert.** `POST /api/proposals/{id}/reuse` stays the only endpoint that
writes reused text (G-AC6). Learning raises what gets *offered*; a human still accepts it.

**3. Re-validate on reuse, always.** Reusing a 2024 answer re-asserts every claim in it as of
today. `reuse_routes.py` already re-runs `validate_draft` on the GET and again on accept, and
`stale_claims` names the expired document. That does not relax because the answer came from
our own export.

**4. No model reads a document and writes into a prompt.** The style brief stays templated
from counts (`style.py`). Edit-derived metrics are counts too. A brief assembled by *reading*
past proposals and injected into every future draft is a permanent prompt-injection channel
(G-6) — that argument is already written into `style.py`'s docstring and it applies unchanged
to anything learned from an edit.

**5. Learning never crosses a workspace.** PRD §6 forbids cross-client training without
opt-in. Every table here carries `workspace_id` inside its unique key — including the conflict
target, because the engine writes with the service role and bypasses RLS
(`docs/known-pitfalls.md`). The counter-intuitive part is that this is a *feature*: a wire-rope
manufacturer's answer library is worthless to an IT services bidder, and the isolation is what
makes the base sharp instead of generic.

## Why not embeddings, and when to revisit

pgvector is already in the stack, so the temptation is real. Three reasons to not reach for it
in v1, and one measurable trigger to reach for it later.

- Lexical matching with IDF weighting is what `select_evidence` and `rank_answers` both use
  today, and evidence selection demonstrably works. Two retrieval mechanisms with different
  notions of "similar" is drift, and drift here shows up as a suggestion panel that disagrees
  with the evidence panel on the same page.
- Government procurement language is *unusually* literal. "Average annual turnover of the last
  three financial years" appears near-verbatim across authorities. This is the rare domain
  where lexical overlap is close to a semantic match.
- An embedding index is a re-index job, a dimension choice, a cost line and a cache-invalidation
  bug, in exchange for recall the floor may not even be losing.

**Revisit when:** reuse coverage (below) plateaus **and** a spot-check shows humans finding
matches the ranker missed. Measure first. `docs/known-pitfalls.md` records what a week of
micro-optimisation bought against one correct region decision — same lesson.

## Does it actually converge? Measure it, don't assert it

"Self-sufficient after 5-6 tenders" is a claim, and this product's whole position is that it
does not make unsourced claims. So it gets a number, computed deterministically from data the
system already has:

- **Reuse coverage** — of the requirements in this tender, what fraction drew a suggestion
  above `_MIN_SIMILARITY`. Rises as the base fills.
- **Acceptance rate** — of the suggestions shown, what fraction a human took. Falls if the base
  is getting noisy; this is the metric that catches loop 4 going wrong.
- **Edit magnitude** — mean token distance from generated to shipped text, per section key.
  This is the honest one. If the system is genuinely learning, a bid manager rewrites less
  each time. If it flatlines, the loop is not working and the meter says so.

Three numbers on one screen, per workspace, with the tender count beside them. If the curve
does not bend by tender six, we will know it, and so will the client.

## Phases

Each phase touches ≤5 files, ships independently, and leaves the product working.

### Phase 1 — close the loop at export · **BUILT**

> Shipped: migration `0030_learning_loop.sql`, `app/deterministic/learning.py::harvestable`
> (the gate), `app/learning.py` (the service), one call from `export_proposal`. No
> `library_documents` row — see the note at the top. Mining reuses nothing from the upload
> path: our own section carries its heading and its semantic key, so there is no blob to
> parse and no model call.


The whole feature in one wiring job.

- **Migration `0030_learning_loop.sql`** — `past_bids.proposal_id uuid references proposals(id)`,
  `past_bids.origin text not null default 'uploaded'` (`'uploaded' | 'generated'`), and
  `unique (workspace_id, proposal_id)` so re-exporting updates rather than duplicates. Backfill
  `origin='uploaded'` for existing rows **in the same migration** — a column only one code path
  writes renders every pre-existing row as the fallback, which is usually the exact bug the
  column was added to fix (`known-pitfalls.md`).
- **`app/learning.py`** (new, ~80 lines) — `harvest_proposal(workspace_id, proposal_id, actor)`.
  Reads `db.get_sections`, keeps only sections with `approved_by` or `edited_by` set (rule 1),
  renders them as `(heading, body)` pages, and hands them to the existing mining path. No new
  mining logic: `mine_answers` already takes `pages` in exactly this shape.
- **`app/proposal_routes.py`** — call it from `export_proposal` after `mark_exported`. Failure
  to harvest must never fail an export; log and move on. The export gate is the product's
  safety story and a learning feature does not get to block it.
- **`app/past_bids_routes.py`** — extract the storage half of `_process` so both callers share
  it. The `template_placeholders` refusal stays on the *upload* path only; our own export
  cannot contain `[Insert Designation]`, and if it somehow does, that is a drafter bug to fix
  at the drafter.
- Tests: a proposal with two approved and one unapproved section harvests exactly two answers;
  a second export updates rather than duplicating; a proposal with zero approved sections
  harvests nothing and does not error.

**After Phase 1, tender #2 is drafted with tender #1's approved answers available.** That is
the user's ask, delivered, before anything below is built.

### Phase 2 — stop destroying the edit signal · **BUILT**

> Shipped: migration `0031_section_original.sql` (backfilled only where `edited_by is null`,
> because for an already-edited row the original is unrecoverable and NULL says so),
> `db.edit_section` seals `original_md` on the first edit, `edit_delta`/`measure_edits`/
> `render_edit_brief` in `deterministic/learning.py`, wired into `style.build_profile`.


- **Migration `0031_section_original.sql`** — `proposal_sections.original_md text`, backfilled
  from `body_md` in the same migration.
- **`app/db.py::edit_section`** — write `original_md` only when it is null (first edit wins;
  the second edit is the human refining their own text, not correcting the model).
- **`deterministic/learning.py`** (new, pure, no I/O) — `edit_delta(original, final) -> dict`
  returning counts: tokens added/removed/kept, sentences touched, whether the rewrite was
  total. Pure function, unit-tested to branch coverage like everything in `deterministic/`.
- **`deterministic/style.py`** — extend `StyleMetrics` with edit-derived fields and add the
  matching templated sentences to `render_brief`. Nothing but counts crosses this boundary
  (rule 4). A client who consistently shortens every generated sentence gets
  *"this bidder tightens generated prose; prefer fewer words per sentence"* — a sentence written
  in `style.py`, chosen by a threshold.
- **`prompts/` untouched in this phase.** Note for whoever builds it: any `prompts/` diff
  requires `/evals` before done (CLAUDE.md). Extending the brief's *content* via `style.py` is
  a code change, not a prompt change — but the eval run is still the honest move, because the
  drafter's behaviour changes either way.

### Phase 3 — rank by what got used, and collapse duplicates · **BUILT**

> Shipped: `answer_usages(count)` joined into `db.get_answers_with_bids`, a bounded usage
> multiplier in `rank_answers`, and `collapse_duplicates` folding near-identical answers
> before the limit is applied. Two pre-existing tests used identical answer text as a
> fixture convenience and were correctly folded by the new behaviour; their setup was
> given distinct prose rather than their assertions weakened.


- **`db.py::get_answers_with_bids`** — join usage counts (`answer_usages`) and a shown-count.
  One query, not an N+1; the pitfalls file is explicit about per-row lookups on these lists.
- **`deterministic/answer_reuse.py::rank_answers`** — a `_USAGE_WEIGHT` multiplier alongside
  the existing `_OUTCOME_WEIGHT`, bounded and gentle. Usage nudges ties; it never overrides a
  materially better textual match, exactly as outcome does not. An answer accepted four times
  is evidence, not proof — the fourth tender may simply have resembled the first three.
- **`answer_reuse.py::collapse_duplicates`** (new, pure) — group answers whose text similarity
  exceeds a high floor, surface the most-used/most-recent as the head, and carry the rest as a
  count. The panel shows *"used in 4 bids"* instead of four rows. This makes repetition read as
  **confidence** rather than as noise, which is the same data doing the opposite job.
- Tests: exhaustive, per `test-strategy.md` — `deterministic/` is CI-gated at 100% branch.

### Phase 4 — make it visible · **BUILT**

> Shipped: `GET /api/learning/maturity`, `reuse_coverage`/`utilisation` in
> `deterministic/learning.py`, and S21 `/knowledge` (`components/LearningMeter.tsx`).
> Coverage is computed with the LIVE ranker so the meter cannot drift from the panel the
> user is looking at.


- **`GET /api/knowledge/maturity`** — the three metrics above, computed deterministically in
  `deterministic/learning.py`, per workspace.
- **Screen S21 `/knowledge`** — tender count, the three curves, and the top reused answers with
  their acceptance rates. Needs a `design_ref`; open `design/tokens.json` before writing UI and
  run `/design-review` after (CLAUDE.md). Note for the DESIGN_SPEC edit: S19/S20 are already
  taken by the Module H capability and schedule-fit screens.
- The screen must say two things out loud, because both are claims we would otherwise make
  silently: **the base contains only what a human approved**, and **a suggestion is never
  inserted without acceptance**. Same discipline as S20's *"Published means recorded by you"*.

### Phase 5 — embeddings, only if Phase 4 says so · **not started, correctly**


Gated on the measured trigger above. Do not start it before.

## Sequencing note

Phase 1 alone answers the request. Phases 2-4 are what make the curve keep bending after
tender three, and Phase 4 is what makes the claim checkable. Phase 5 may never be needed —
that is a success, not an omission.

## Deliberately not doing

- **Fine-tuning a model per client.** Cost, latency, an eval gate per customer, and the client's
  proprietary bid content baked into weights we then have to reason about deleting. The answer
  library gets the same benefit with provenance attached, and provenance is the product.
- **Cross-client learning.** PRD §6 forbids it without opt-in, and the wall (F13) is why a
  government buyer can be sold the evaluate product at all. Not a feature to revisit lightly.
- **Learning verdicts, gates or comparators.** PRD §2.4 is normative. The system may learn what
  to *write*; what it *decides* stays deterministic. An eligibility comparator that drifted
  toward a client's past answers would be a comparator that tells each client what they want
  to hear.
- **Mining unapproved AI prose.** Rule 1. This is the one that will be argued for — it would
  make the coverage number rise fastest, and it is the exact mechanism by which the feature
  would quietly fail.
- **Auto-setting `outcome` from anything.** It stays user-set. We cannot see an award notice,
  and a guessed win steers every future suggestion (`0027`'s own column comment).
- **Learning the vendor profile from prose.** Identity and financial facts come from structured
  profile data, never from an evidence chunk — that is how "Merdian Technology" reached a real
  government submission (`known-pitfalls.md`).

## Assumptions to veto

| # | Assumption | Confidence |
|---|---|---|
| 1 | Enough sections get individually approved for rule 1 to leave a usable harvest | **Medium, and this is the gate on Phase 1.** If bid managers approve in bulk at the end, the filter still works; if they never approve at all, the export gate would already be blocking them, so the signal exists |
| 2 | A client runs 5-6 tenders through the product before judging it | Medium — until then the manual `past-bids` upload is the cold-start path, and it already works |
| 3 | Lexical matching holds as the base grows to hundreds of answers | Medium-high — IDF weighting handles vocabulary growth; the measurable trigger in Phase 5 is what catches it if not |
| 4 | Edit magnitude actually falls as the base fills | **Unverified, and it is the honest test of the whole idea.** Phase 4 exists to find out rather than to assume |
| 5 | Near-duplicate collapse can be done lexically without merging two genuinely different answers | Medium-high — a high floor plus keeping the collapsed rows addressable makes a wrong merge recoverable |
