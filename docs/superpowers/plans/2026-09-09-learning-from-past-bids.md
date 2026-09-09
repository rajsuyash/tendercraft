# Learning From a Company's Past Bids — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new customer uploads 5–10 of their own past bid packages on day one, and from that alone the system can draft a credible fresh proposal in their voice, with their confirmed facts, citing their evidence — and can state honestly when it cannot.

**Architecture:** Nothing here is fine-tuning. Three separate corpora get populated from one intake: **confirmed facts** (structured, human-promoted, the only thing eligibility may read), **evidence** (anchored source units the drafter may cite), and **measured style** (deterministic sentence statistics, never model-authored). A fourth product — reusable **answers** — is mined from the customer's own prior responses. The intake is the only new user-facing action; everything downstream already exists in some form.

**Tech Stack:** Python 3.12 / FastAPI / pytest · Supabase Postgres + RLS · Next.js 15 / TypeScript / Vitest · macOS Vision (local proof) then a Linux OCR adapter (production)

---

## Read this before anything else: the trust boundary is already broken

`app/analysis.py::decide()` is documented as "the deterministic decision layer". Verified 2026-09-09:

```python
passed = compare_numeric(ev.actual_value_cr, ev.required_value_cr, ev.operator)
```

`compare_numeric` is deterministic. **`ev` is `ModelEval` — the model's output.** `actual_value_cr` is declared in the model's JSON schema at `pipeline/schemas.py:46` and read from the raw response at `pipeline/analyzer.py:73`. So the bidder's turnover, the tender's threshold and the operator are all model-written, and the arithmetic step in the middle makes it look deterministic. The `else` branch passes `Verdict(ev.model_verdict)` through behind a confidence gate, and `ev.exemption_applies` lets the model grant exemptions.

This is a live PRD §2.4 violation and it is the same failure already recorded in `docs/known-pitfalls.md` for `is_financial`: *never let a model report the field that decides its own gate.* Here it reports both operands.

**Why this gates the whole plan.** The feature the owner asked for is "learn the facts of the business". That reads like it would *introduce* the risk of model-derived facts reaching eligibility. It does not — the path is already open, and this plan would increase the volume flowing through it. **M4 closes it. No milestone that writes facts may ship before M4.**

---

## What is true today, measured not assumed

| Claim | Evidence |
|---|---|
| Tender ingest teaches nothing reusable | 5 packages ingested → 5 `tenders`, 861 `criteria`, 98 `tender_line_items`, 347 `matrix_unmapped`, and **0** `library_documents` / `past_bids` / `answers` / `style_profiles` |
| Every criteria read is tender-scoped | `db.get_criteria(tender_id, workspace_id)`; no cross-tender reader exists |
| Both learning mechanisms share one input | `POST /api/past-bids` writes `answers` **and** a `library_documents` row with `doc_type='past_proposal'`; `db.get_past_bid_texts` reads exactly those |
| Style is measured, not written | `app/deterministic/style.py`, ≥40 sentences, fixed-phrase rendering — deliberately, because a model-authored brief from untrusted documents is a permanent injection channel |
| Retrieval is lexical, not pgvector | `pipeline/retrieval.py` ranks by weighted token overlap. `docs/architecture.md` and `CLAUDE.md` both claim pgvector. **The docs are wrong.** |
| Draft generation never auto-consults `answers` | Suggestions are a separate GET; G-AC6 requires explicit acceptance |
| OCR does not exist, and it is the binding constraint | A real 5-tender customer folder: 480 pages, **48% carried extractable text**, and the unreadable half was almost entirely the *bidder's* own documents — exactly this feature's raw material |
| Customer folders mix buyer and bidder documents, and filenames lie | A file named `ATC.pdf` contained the bidder's Factory Act licence |

---

## Constraints. A milestone that breaks one does not ship.

1. **PRD §2.4** — no model output decides a verdict, gate or coverage count.
2. **Facts are candidates until a human confirms them.** Model confidence, successful OCR, agreement across several bids and a matching citation are **none of them** confirmation.
3. **Cite-or-flag (B-FR1)** — every generated sentence resolves to a source or is flagged. Citation proves *addressability*, not entailment.
4. **B-FR3** — financial values transclude from confirmed structured facts; the drafter never authors an amount.
5. **G-6** — document content is untrusted: it never parameterises a fetch, a tool call or a prompt instruction.
6. **Circular grounding** — a proposal *we* generated never becomes retrievable evidence. The existing asymmetry is correct and must be preserved: a customer-uploaded past bid legitimately becomes a `past_proposal` library row; an export-harvest deliberately does not.
7. **ET-6** — workspace-scoped everywhere; the engine writes with the service role and bypasses RLS, so the scope lives in the query too.

---

## Milestones

Each is independently shippable and demoable. Batches of ≤5 files including tests, per `CLAUDE.md`.

### M1 — Recover one scanned bidder document *(proves the binding constraint is solvable)*
**Files:** `app/ocr.py` · `tools/vision_ocr.swift` · `app/ingest.py` · `tests/test_ingest.py`

Bounded OCR interface: page-count, pixel, timeout, concurrency and retry limits. macOS Vision adapter as the local proof — `pdftoppm` and `swiftc` are both already on the dev machine, so this costs nothing and no document leaves the laptop. Fixed executable arguments and server-generated paths: document text can never select a command.

The existing `<20 characters` rule catches empty scans but misses a page carrying only a readable header, so extraction status becomes explicit per page rather than inferred from length. Unreadable pages persist as unreadable instead of vanishing.

**Demo:** the misleadingly-named `ATC.pdf` licence yields page-anchored text. No profile or knowledge writes at all.

### M2 — Production extraction *(the macOS path is a proof, not a deployment)*
**Files:** `app/knowledge.py` · `app/ingest.py` · Linux OCR adapter · `Dockerfile` · parser/OCR tests

The engine image is Linux; Vision is not shippable. Add a Linux adapter and validate it against the same pages M1 used. DOCX support reuses the installed `python-docx` but must read paragraphs **and tables in document order** plus header/footer content — a compliance annexure is mostly tables, and the two `.docx` files in the sample folder are rejected outright today. Use paragraph/table/cell locators; never invent Word page numbers.

### M3 — Durable sources and batch intake
**Files:** `0040_knowledge_sources.sql` · `0041_knowledge_imports.sql` · `app/knowledge_import_routes.py` · `app/knowledge_import_worker.py` · `pipeline/package_classifier.py` + `prompts/package_classifier.md` · `apps/web/components/PastBidUpload.tsx`

Immutable originals with checksum and extraction revision; citation identity binds to source revision + span, never a mutable re-chunking ordinal. Import returns `202` with a persisted job — a 480-page import must not run inside the upload request.

The classifier labels content `buyer_requirement | bidder_response | bidder_evidence | blank_template | unknown`, at **page/block** level as well as document level, because one compliance table holds both the buyer's question and the bidder's answer. It separates **author** from **subject**: a government-issued licence is bidder evidence without being bidder-authored prose. Filenames are hints only. Output is schema-allowlisted with supporting spans; no tools, no document-derived URLs. The user confirms roles in a batch review, and unresolved material stays quarantined — **buyer text must never reach the style corpus.**

**Demo:** upload five packages, refresh mid-job, retry one failure, confirm roles, open any original.

### M4 — Reviewed facts, and close the eligibility bypass *(gates everything after it)*
**Files:** `0042_profile_fact_review.sql` · `app/profile_fact_service.py` · `app/analysis.py` · `pipeline/analyzer.py` · `apps/web/components/ProfileFactReview.tsx` + comparator tests

`profile_fact_candidates` / `profile_fact_versions`, states `pending_review | confirmed | rejected | superseded`. Conflicting candidates stay pending with a stated conflict reason rather than one silently winning. Confirmed values project into the existing `profile_financials`, `vendor_profiles`, `certifications`, `experience_records`.

**The bypass fix:** `decide()` stops reading `ev.actual_value_cr`. Comparators bind to *confirmed profile records* against *confirmed requirement operands* — field, operator, threshold, unit, fiscal years, reference date. A model may propose a binding; it may not be one. Missing facts, unresolved bindings or unsupported predicates → `needs_review`, never zero, never `False`, never an automatic Fail, never a model-selected Pass. The model may not grant an exemption.

Before confirmation a candidate earns **no** comparator input, no transclusion, no readiness credit, and the drafter must not restate it from the source material either. Missing required fields become named placeholders: "Confirm turnover for FY24."

**Adjacent bypass, same class:** `app/knowledge.py` persists a model-derived `valid_to` that `db.get_valid_library_docs()` uses as a **hard filter**. Stage and confirm validity dates too, and evaluate them against the target tender's applicable date rather than today.

**Demo:** an extracted turnover changes no verdict until confirmed; afterwards the comparator uses the confirmed record; an adversarial model value cannot move it.

### M5 — Anchored answers and a real style corpus
**Files:** `0043_answer_sources.sql` · `app/past_bids_routes.py` · `app/deterministic/answer_mining.py` · `pipeline/answer_miner.py` · `app/deterministic/style.py` + tests

**Remove the 20,000-character truncation** in `past_bids_routes.py`. It preserves cover pages and discards methodology and experience prose — precisely the writing worth measuring. Keep full anchored text; bound each *model request* separately instead.

Measure style only over confirmed **customer-authored response blocks**: exclude buyer clauses, templates, certificates, duplicated boilerplate and any known generated proposal. Rebuild automatically when a confirmed import completes; keep the manual endpoint. Store corpus revision and style version.

Keep `MIN_SENTENCES = 40` and the fixed-phrase rendering. **Show the actual eligible sentence count** — 5–10 substantive written bids may clear 40; 5–10 packages of forms, scans and certificates may not, and the difference must be visible rather than assumed.

Preserve deterministic structure mining first and verbatim validation for model-mined answers. The current model miner discards the page argument; carry document/unit/span through to persistence.

### M6 — A fresh proposal that uses all of it
**Files:** `app/reuse_routes.py` · `apps/web/components/ReuseSuggestions.tsx` · `app/proposal_routes.py` · `pipeline/drafter.py` + `prompts/drafter.md` · citation/transclusion tests

Style currently reaches `pipeline/section_drafter.py` only — per-criterion `draft_response()` gets none. Wire the same measured brief into both, with tender-mandated wording taking precedence.

Suggestions may be fetched automatically during preparation, but **acceptance stays explicit** (G-AC6): show the selected answers and their destinations, persist `answer_usages` *before* accepted text enters generation context. Accepted answers enter as untrusted reference material and are re-resolved to their source passages — a lexical match against some other document is not proof of support.

### M7 — Honest readiness
**Files:** `app/deterministic/knowledge_readiness.py` · `app/reuse_routes.py` · `apps/web/components/LearningMeter.tsx` + eval fixtures · architecture docs

| Dimension | Measure | Complete means |
|---|---|---|
| Facts | confirmed applicable inputs / required inputs for the target tender | 100%, zero unresolved bindings or conflicts |
| Evidence | obligations with a resolvable, reviewed, applicable source / obligations | 100%; unreadable, pending-validity and generated sources score zero |
| Style | eligible sentences / **40**, with corpus revision and contributing bids | ≥40; correction learning separately needs 5 edits |
| Answers | candidates shown separately from accepted, source-valid answers | every user-selected reuse target resolved; zero selected = N/A, not 100% |

Without a target tender, facts and evidence read **not assessed** — not zero, not complete. **Never equate upload count with readiness.** `mandatory_coverage` counts placeholders as addressed and must not be presented as evidence sufficiency. Readiness is not eligibility and not an export gate.

Correct `docs/architecture.md` and `CLAUDE.md`, which both claim pgvector.

---

## Retrieval: measure before buying

Start with the existing lexical retrieval (4 chunks per criterion, 12 per narrative section, answer similarity floor 0.20). At 5–10 documents it is cheap — but cheap is not the same as sufficient: synonyms, OCR noise and non-English text defeat token overlap, and this corpus has all three.

Replace the zero-match "return everything" fallback with explicit no-match behaviour. Build a human-labelled held-out query set including paraphrases, missing evidence and negatives. Target supporting-source recall@4 ≥ 90%; investigate every miss touching mandatory evidence. **Improve normalization and controlled synonyms first. Add vector retrieval only if measured misses justify it** — and quote no cost until corpus size and provider are fixed.

---

## Deliberately not building

- **Fine-tuning, autonomous memory summaries, model-authored style briefs.** Unnecessary at this corpus size and a permanent instruction-contamination channel.
- **Automatic profile promotion at any confidence threshold.** That is exactly how extraction gets laundered into eligibility — the failure M4 exists to close.
- **Automatic answer insertion.** Violates G-AC6.
- **Treating the 861 workspace criteria as business knowledge.** Buyer requirements are not bidder evidence. They are useful as historical requirement queries and retrieval evaluation cases; nothing more.
- **Vector infrastructure before a retrieval benchmark shows it is needed.**
- **A macOS-dependent production ingestion service.**
- **"Ready after five bids" badges.**
- **Any change to Evaluate surfaces or cross-product data access** (F13).

---

## First commit

`feat(ingest): add bounded local Vision OCR fallback with preserved PDF page anchors`
— `app/ocr.py`, `tools/vision_ocr.swift`, `app/ingest.py`, `tests/test_ingest.py`.

Prove recovery on one scanned bidder licence. No profile promotion, no eligibility side effects, no knowledge writes. It is the smallest change that tests the assumption everything else rests on: that the unreadable half of a customer's folder is recoverable at all.

---

# AMENDMENT — 2026-09-09, after adversarial review

An independent review attacked this plan and found the memory layer under-specified. Two of its
findings were verified against the code and are **live defects**, not design gaps.

## Verified live defects, both on hard gates

**`app/sections.py:158` — the turnover transclusion answers the wrong question.**

```python
avg = sum(float(f.get("turnover_cr") or 0) for f in fins) / len(fins)
```

Averages **every stored FY**, labels it `"CA-certified turnover statement (N FYs)"`, and emits
the token `profile_financials:avg.turnover_cr` — which names no FY window and no constituent
versions. The UCIL tender ingested 2026-09-09 asks for *"Minimum Average Annual Turnover of the
bidder (For 3 Years)"*. Confirming FY26 silently changes the number answering a FY23–FY25
requirement. This is a financial value under a CA-certified label on a non-overridable gate.
**A fact token must bind an FY set and the exact fact versions, or transclusion is theatre.**

**`app/reuse_routes.py::_apply()` — the G-AC6 receipt is written last.** `append_reused_section_text`
and `upsert_response` both run before `record_answer_usage`. A failure between them leaves reused
text in a proposal with no record it was accepted, and that receipt is the only evidence no
suggestion entered a draft unaccepted. Acceptance must be one transaction against an exact
answer version, with an idempotency key.

## The amendment: M4 becomes a memory-and-dependency contract

**M4's deliverable changes from "reviewed facts" to "versioned memory with recorded
dependencies".** Facts alone do not answer the question that matters on tender N+1: *what did
this run consult, what was it permitted to use, and what has changed since?*

**New tables** (proposed names): `requirement_binding_versions`, `profile_fact_versions`,
`answer_versions`, `style_profile_versions`, `workspace_memory` (one monotonic revision per
workspace), `memory_snapshots` + `memory_dependencies` (immutable run receipts, typed
`transcluded | cited | context_supplied | style_used | assembled_from`). Typed foreign keys,
workspace-composite — not a polymorphic id bag.

**`requirement_binding_versions` is what M4 was missing.** `criteria.confirmed` confirms a
criterion *row*; it does not confirm a field, operator, threshold, unit, FY set, aggregation,
reference date or exemption predicate. Those columns do not exist, so changing `decide()` alone
cannot fix the bypass. A confirmed binding carries all of them plus reviewer and time. A model
may propose one from an allowlisted predicate registry; only a human's confirmation makes it
executable.

**Preserve base result, exemption result and effective verdict separately.** Today counts can
show Fail while `recommend()` treats an exemption as Pass.

**The decisive regression test is invariance:** hold confirmed records and bindings fixed,
arbitrarily vary every model evaluation field, and assert that verdicts, exemptions,
recommendation and coverage do not move. Note that existing `test_analysis.py` cases currently
*bless* model-supplied operands and model-granted exemptions — those tests encode the defect and
must change with the code.

**Route every profile mutation through the fact service.** `analyze_routes.update_profile()`
writes the tables directly and `db.replace_profile_collection()` deletes and reinserts whole
collections; adding versions beside that leaves one route changing current truth with no
provenance and no invalidation. Existing tables become projections. Legacy values stay visibly
unreviewed — migration must not manufacture confirmation.

**Close the third G-AC6 hole.** Uploaded past bids are `past_proposal` library rows, so
`do_generate()` can retrieve their response prose through ordinary evidence retrieval without
touching `answers` or acceptance. A reviewed recall view must exclude response blocks that
require acceptance, separately from confirming a document's role.

## Invalidation — four properties, not one `valid_to`

Separate **historical addressability**, **human confirmation**, **applicability to a date**, and
**freshness of a consumer**. `db.get_valid_library_docs()`'s "null means evergreen" becomes
reviewed states: `unknown | bounded | evergreen | revoked`.

A new FY is a **new key**, never a supersession. A corrected FY supersedes within the same
qualified key and flags dependents. An approved section whose fact changed keeps its body,
baseline, receipt and historical approval — but its current revision goes stale and says why:
*"FY2024–25 turnover was corrected. This section uses version 3; version 4 is confirmed."*

Two mechanisms required: a durable queue for notifications, and **synchronous validation at
recall, approval and export**. The queue is not a safety boundary, and date passage must trigger
checks without waiting for a write.

## Conflicts

Two turnover values for the same qualified FY key: **retain both, never average, vote or take
the newest.** A human picks, identifies a restatement, or corrects the qualifiers. A newer
model-extracted contradiction does **not** revoke a confirmed fact — otherwise extraction
decides a gate by the back door. Concurrent confirmations use compare-and-swap on the key
revision.

Fact keys must prevent false conflicts: turnover keys on legal entity + FY window + accounting
basis + currency; certificates on holder + scheme + issuer + identity + site/scope.
**"Latest turnover" is a selector, never a stored number.**

## Embeddings: still no

Fix the lexical baseline first — Unicode-aware tokenization (`[a-z0-9]+` discards Devanagari,
and these tenders are bilingual), OCR normalization, controlled aliases, remove the
all-documents fallback, and stop `draft_response()` trimming 1,500-char chunks to 1,200, which
can cut the supporting sentence *after* retrieval chose it. Only if a human-adjudicated held-out
set still misses the 90% recall@4 target, and the failures are semantic, consider hybrid.

## Sequencing correction

"Independently shippable" was overstated. M5 depends on M3's source identities, M6 on M4's fact
authority and M5's provenance, M7 on reviewed support relationships no milestone creates. Ship
them incrementally **behind disabled capabilities**, not as independent behaviour. M1 is a spike,
not a production increment. Also: `knowledge.build_document()` truncates at 20,000 chars too —
fixing only `past_bids_routes.py` leaves the second path.

## The honest ceiling, restated

The likely disappointment is the **first import**: five packages can yield hundreds of pages and
very little usable memory — buyer wording, duplicate forms, expired credentials, commitments
specific to one contract. Show that inventory and the review work. Do not promise "upload five
bids and the system knows your business."
