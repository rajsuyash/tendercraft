# Customer-readiness plan — TenderCraft bidder product

**Date:** 2026-09-15 · **Inputs:** `docs/audit/2026-09-15-product-audit.md` (this repo's audit: live production walk + four code traces) and `docs/reviews/2026-09-15-codex-product-audit.md` (outside review, code-only). **Status:** proposed; owner sign-off needed on §5 before R1 is scheduled.
**Definition of "ready for real customers":** a bidder who is not Usha Martin can sign up, describe their company mostly by uploading documents, see a short list of tenders with reasons, get a bid/no-bid card that is right on their own product line, and export a submission-shaped document in which every statement about the bidder is true. Nothing in the product asserts something it did not observe.

---

## 0. Execution log — 2026-09-15, shipped

Five commits, pushed to `build/tendercraft` and deployed: engine revision
`tendercraft-engine-eu-00061-rh7`, web revision `tendercraft-web-eu-00065-pvg`. Verified on
production as FIX-1 after the deploy.

| Phase | Task | State |
|---|---|---|
| audit | The nine defects found by the audit itself (deadline extraction, cert validity, DOCX cover, digest fields, hub nav, login copy, env names, `Form()` binding, section-approval authz) | **shipped** |
| R0-1 | Rubric verdict removed; "Document completeness"; rubric is a GET; estimator button gone | **shipped** |
| R0-2 | Form 12 built from the schedule fit, three outcomes, never a nil default | **shipped** |
| R0-3 | Feed says "not checked" when no bid document was read | **shipped** |
| R0-4 | Regeneration keeps human edits and accepted reuse; any rewrite voids its approval | **shipped** |
| R0-5 | `StageProgress` stops drawing checkmarks it cannot observe | **shipped** |
| R0-6 | Navigation below `lg` (`[data-nav-toggle]` + drawer); feed table scrolls instead of colliding; long refs wrap | **shipped** |
| R0-7 | Deadline backfill | **void — no data source.** No tender was ever linked to a pursuit (the `Form()` bug), and the six existing tenders are not in the corpus at all. Nothing persists page text after ingest, so the new parser cannot be re-run over them either. Replaced by a manual entry path (below). |
| R0-7 | `RESEND_API_KEY` / `RESEND_FROM` on the engine | **blocked — the key is not on disk.** Confirmed absent from the live service's environment; digests and assignment emails cannot send until it is set. |
| R0-7 | Move FIX-1 out of the customer's workspace | **not done — owner's call** (§5.3). The seeded test user still operates inside Usha Martin's workspace. |
| R0-8 | Commit; four new pitfalls appended | **shipped** |
| — | `PATCH /api/tenders/{id}` takes a deadline; readiness header sets it, in IST | **shipped** (not in the original plan; replaces the void backfill) |
| R1-4 | One blocker list: readiness reads the export gate's decision | **shipped** |
| R2-1 | Closed tenders filtered by the database before the limit; true closed count | **shipped** |

**What R2-1 measured on the live workspace, which is the finding of the day:** 4,221 of 4,310
in-scope matches had already closed. The page asked for 100 rows best-fit-first and the browser
filtered afterwards, so almost every row the server chose was a closed tender and every open
one past position 100 was unreachable — no pagination, no search, no error. The feed now opens
on wire-rope tenders closing tomorrow.

---

## 0b. Execution log — 2026-09-16: the two changes that mattered most

Both of the changes named above as "the two that matter most" are shipped, plus the verdict
rewrite that sat between them. Engine revision `tendercraft-engine-eu-00069-wz5`, web revision
`tendercraft-web-eu-00070-599`. Migrations 0042–0046 applied to production, each confirmed
SERVED rather than merely accepted. Verified on production as FIX-1 after every deploy.

| Phase | Task | State |
|---|---|---|
| P1 | The dead ends: export delivers bytes, the download link reads the server's own decision, the verify queue stops being stricter than the lock gate, sweep failures are visible | **shipped** |
| P2 | Requirement classification (`deterministic/requirement_kind.py`, migration 0042) — gate / obligation / instruction / form / spec, computed at read time, human-overridable | **shipped** |
| P3 | The verdict is computed from facts (`deterministic/facts.py`), the model describes the requirement and never sees the bidder, exemptions are grounded, only gates vote, the working is persisted | **shipped** |
| P3-e | B9 — the FY window reaches the PQ sheet | **shipped** |
| P4 | Export binds to the text that was approved (content hash, migration 0043), unverified sections block, a re-save cannot launder a financial flag, "ready" knows the document was read (migration 0044) | **shipped** |
| P5 | The document is shaped by the tender (`deterministic/outline.py`, migration 0046), three new catalogue entries, the matrix stops claiming compliance, the rubric renormalises | **shipped** |
| — | Reading cache (migration 0045) | **shipped** — not in the plan; found by verifying P3 on production |

**Three measurements from the live workspace, which are the findings of the day.**

*Zero of eighteen.* On the Oil India wire-rope bid, eighteen criteria were mandatory and
therefore voted on the card. Four were post-award inspection duties, four were quoting
instructions, four were blank declaration forms, three were rules about how you may bid, two
were reseller duties, one was GTC acceptance, and **none was a pre-bid eligibility gate**. The
card read NO-BID on a tender squarely inside the bidder's product line. It now reads "nothing
disqualifies you", with all 35 requirements listed under what you do about them.

*The verdict moved between identical runs.* Found by verifying P3 on production rather than by
reading code: two analyses minutes apart produced different cards. The decision layer is pure
arithmetic with no model near it — what moves is whether a clause IS a gate, which depends on a
model reading. Six extractions of one OEM-authorisation clause returned `none` at 0.90 four
times and `certification_valid` at 1.00 twice, confidently on both sides, so no confidence
threshold separates them. **Moving the model out of the decision was necessary and was not
sufficient.** Fixed by reading once and storing against a hash of the criterion text plus the
prompt file's digest; three consecutive production runs are now byte-identical where two in a
row were not.

*Four patterns fired on wire rope.* The outline's signals were measured against 2,000 live
criteria before being trusted. `\bapi\b` matched 23 times and every hit was **API Specification
9A**, the petroleum institute's rope standard; `platform` matched the TReDS and SFMS banking
rails; `application` matched a rope description; bare `training` matched a local-content
declaration. All four are gone, and the services tender that needs those sections still gets
them. The wire-rope proposal went from 20 sections to 14, and the rubric from nine weighted
dimensions to six that sum to 100.

**Still outstanding, and none of it is engineering.** `RESEND_API_KEY`/`RESEND_FROM` are absent
from the engine service and not on disk, so digests cannot send. The FIX-1 test user still
operates inside Usha Martin's real workspace. Both are §5.3 owner decisions.

---

## 1. Where the two audits agree, differ, and what was disputed

**Both reviews reached the same top three independently** (one from live screens, one from code alone): the proposal template is aimed at a customer this product does not have; the bid/no-bid signal is not trustworthy; the export gate does not bind to the exact document a human approved.

| Finding | This audit | Codex | Resolution |
|---|---|---|---|
| Fixed 17-section IT template applied to goods tenders | P0 (seen: "Training & Capacity Building" on a rope bid) | P1 §8, "structurally right" in §D | **Agreed. P0.** The biggest single gap. |
| Bid/No-Bid unreliable | P0 — false NO-BID on core product; obligations and instructions scored as gates (`analysis.py:104-109`, `eligibility.py:98-101`) | C1 — numeric branch trusts model-supplied actual values; exemption without clause; evidence ids not resolved | **Two different defects in the same card, both confirmed.** Codex's C1 is reachable through the real schema: `decide()` compares `ev.actual_value_cr` and `ev.required_value_cr` supplied by the model with no confidence or evidence check (`analysis.py:57-63`); both are plain nullable numbers in `CRITERION_EVAL_SCHEMA`. So the model can assert the bidder's turnover and the comparator blesses it. Ours is over-inclusion of non-gates. Fix together (R1-2). |
| Export binds to approvals, not content | P0 #6 — regenerate keeps `approved_at`, drops edits | C2 — plus: unverified non-financial claims do not block; save clears flags without revalidation; viewer could approve | **Agreed, Codex's list is more complete.** Viewer hole fixed today. Rest is R1-3. |
| "Ready" while export blocks | Not found (live tender showed "Not ready 40%") | C3 — reproduced 100% / `can_submit=True` with a mandatory placeholder; §D asked whether it is user-visible | **Confirmed in shape:** `submission.compute` accepts `hard_blockers` but `submission_state` never passes the export gate's list (`readiness_routes.py:161-171`); `SubmissionMeter` renders `can_submit`. User-visible when it happens. R1-4. |
| Generic "Technically disqualified" | P2 (score page) | C4 — P0 remove now; §D asked what the screen renders | **Confirmed live:** `/proposals/:id/score` renders "50.3 / 100 — Technically disqualified — below the 65% aggregate" against a MeitY IT rubric on a rope tender. Contain in R0. |
| Automatic "no deviations" (Form 12) | Noted under template | C4 — P0 | **Agreed.** Contain in R0. |
| Feed capped at 100, closed rows crowd it | P1 | C5 — P1; §D: filter first, paginate second | **Agreed, same remedy.** R2-1. |
| Upload `title`/`pursuit_id` never arrive | Not found by tracing | B1 — confirmed §V | **Fixed today** with a multipart contract test. This also made our deadline-from-pursuit fallback reachable. |
| Deadline never extracted | P0 (6/6 tenders) | B7 | **Fixed today** for new uploads (document first, portal second). Backfill pending. |
| DOCX cover "Bidder" | P0 #3 | B8 | **Fixed today.** |
| Turnover window never bound | P0 #3 | B9 | Agreed. R1-2. |
| Certs without expiry printed EXPIRED | P0 #3 (live) | — | **Fixed today.** |
| Digest drops deadline/value; mail unconfigured in prod | P0 #8 (live + code) | — | Digest **fixed today**; env is an ops task (R0). |
| Sub-screens unreachable for live tenders | P0 #5 | — | **Fixed today** (hub nav). |
| Over-extraction: 896 items awaiting verification, boilerplate as criteria | P0 #7 | Partly (§7: no correction of fields; keyword denominator) | Ours is the root cause behind Codex's C3 denominator note and our own #1. R1-1. |
| Model confidence discarded; value ignored in ranking | P1 | §6 | Agreed. R2-2. |
| Pursue does not fetch documents | P1 | §2, §12 step 4 | Agreed. R2-3. |
| Source documents not retained; library PDFs get no OCR; DOCX tables dropped | Noted (docs destroyed on ingest) | B5 + missing feature 4 | Agreed; Codex found the table-loss. R3-4. |
| Inbound emails create no opportunity; bid actions have no UI | Endpoint-without-UI list | B6 | Agreed. R4-3. |
| No signup / onboarding starts at upload | P0 #8 | P1 + missing feature 1 | Agreed. R4-1. |
| Mobile navigation absent below `lg` | Missed | P1 | Agreed; small. R0. |
| `StageProgress` advances on a timer | Missed | P2 | Confirmed (`StageProgress.tsx:33`). R0 copy fix; real progress needs the jobs table (R3-1). |
| "none stated" when the document was never read | Seen on every IREPS row, misdiagnosed | §6 "unknown presented as absence" | Codex is right. R0. |
| Corrigendum impact tracking | Missed | Missing feature 7 | Agreed; after R3. |
| Submission package (attachments, forms, BOQ, manifest) | Partial | Missing feature 6, XL | Agreed; last phase. |
| Test user lives in the customer's workspace; French default | Live only | — | Decision item (§5). |
| Settings decorative; three matrices; seven coverage numbers | Both | Both (§5, §8) | R3-3 consolidation. |

**Disputed items, resolved:** D1 real and reachable → R1-2; D2 real and user-visible → R1-4; D3 confirmed on screen → R0; D4 agreed → R2-1.

---

## 2. Gates for "ready"

Release to a second customer only when all six hold, each verified at its tagged layer (`docs/test-strategy.md`):

| # | Gate | Verified by |
|---|---|---|
| G1 | No sentence about the bidder in an exported document is unsupported: certs, turnover, identity and deviations come from structured facts or an explicit human decision, never a default | `/verify-api` on export + unit tests on `sections.py`, `export_gate.py` |
| G2 | Bid/No-Bid on a partner-labelled set of 20 tenders: zero false NO-BID on in-scope tenders; every FAIL cites a pre-bid gate | `/evals` golden set `eligibility-gates` (new) |
| G3 | Readiness, export gate and DOCX download agree: one blocker list, one `can_submit` | integration test asserting the three share `export_gate.decide()` |
| G4 | A new company completes signup → company facts (≥70% proposed from uploads) → first shortlist without help | `/verify` journey as a fresh user |
| G5 | Feed shows ≤25 open, scored, explained rows per day per workspace; a known reference is findable by search | `/verify` + partner rating sample ≥60% "worth a look" (F-AC2) |
| G6 | Upload → draft with no clicks in between on a clean package; happy path to DOCX ≤ 8 clicks for a solo writer | `/verify` click count |

---

## 3. The plan

Effort: S ≤ 1 day · M ≤ 1 week · L 2–3 weeks · XL > 3 weeks, one engineer. Milestone ids continue the discovery PRD's sequence (M13 was deleted).

### R0 — Containment and ops (this week, S each) → M14

Stop the product asserting things it did not observe. No new capability.

| Task | Change | Files | Done when |
|---|---|---|---|
| R0-1 | Remove "Technically disqualified" and the 45/65 thresholds; relabel the rubric "Editorial checks" and drop the IT-rubric heads from non-services tenders; hide the estimator hero until ≥30 outcomes exist | `rubric_service.py`, `deterministic/rubric.py`, `RubricCard.tsx`, `EstimateView.tsx`, `score/page.tsx` (compute on click, not on GET) | Score page shows no verdict word; no rubric POST on page load |
| R0-2 | Form 12: replace the default "confirms no deviations" with the schedule's `spec_match` result — one row per deviation with the clarification status, or "No deviations recorded against N assessed parameters; M parameters not assessed" | `sections.py:249-261`, `spec_service.py` | Unit test: a deviation in `spec_parameters` appears in Form 12 |
| R0-3 | Feed "none stated" → "not checked" when no bid document was read; "none stated" only when the document was read and stated none | `OpportunityFeed.tsx:1050`, eligibility payload carries `document_read: bool` | DOM assertion |
| R0-4 | Regenerate: skip sections with `edited_by`; reset `approved_at/approved_by` on any body change; never overwrite a criterion response accepted via reuse | `proposal_routes.py:155-176`, `:63-72`, `db.py:281` | Tests: regenerate leaves an edited section; approved section loses approval when body changes |
| R0-5 | `StageProgress`: show elapsed time and "reading…" only; no checkmarks the system did not observe | `StageProgress.tsx` | DOM |
| R0-6 | Responsive nav below `lg` (toggle + drawer, GLB-D2) | `Sidebar.tsx`, `layout.tsx` | screenshot @1024, @768 |
| R0-7 | Ops: `RESEND_API_KEY`, `RESEND_FROM` on the engine service (`--update-env-vars`); deadline backfill SQL for existing tenders from linked `opportunities.closing_at`; move FIX-1 out of the UML workspace into a seeded demo workspace; set its locale to `en` | `docs/deploy.md`, one migration-style script | `/settings` no longer says "no mail server"; dashboard shows deadlines |
| R0-8 | Commit today's nine fixes; append pitfalls: Form-vs-query binding, unknown≠absent, cert validity tri-state, test stubs must carry the real row shape | git, `docs/known-pitfalls.md` | CI green |

### R1 — Truth gates (2–3 weeks) → M15 · satisfies G1, G2, G3

The product must be right before it is fast.

| Task | Change | Files | Effort | Done when |
|---|---|---|---|---|
| R1-1 | **Requirement classification.** Every extracted item gets `kind ∈ {gate, obligation, instruction, form, spec}` — deterministic rules first (section headings, "shall submit", "bidders to note", declaration markers already found by `drafting.template_placeholders`, BOQ rows), model proposes only for the residue and only from the enum (G-6). `criteria.kind` column; migration | `pipeline/extractor.py`, `deterministic/` (new `classify.py`), migration, `readiness.py`, `ReadinessHub.tsx` | L | On the UML package: gates ≤ 10 of 35; instructions render as a checklist, forms as "to fill", specs as the schedule; verification queue shrinks to low-confidence *gates* |
| R1-2 | **Bind eligibility to facts.** `decide()` takes `actual_value` from `profile_financials`/`certifications`/`experience_records` computed in Python (FY window from the criterion's stated years; average, not all-years), never from the model; exemption only with a resolvable `exemption_clause` anchor; evidence ids resolved against real rows; only `kind=gate` items enter the verdict; a needs-review on a non-gate never drags the recommendation; output gains `reasons[]` and `risks[]` | `analysis.py`, `deterministic/eligibility.py`, `pipeline/analyzer.py` (schema loses `actual_value_cr`), `sections.py` (Form 1 turnover now bound: closes B9) | L | Golden set `eligibility-gates` (20 partner-labelled tenders, ≥ 10 from UML's own packages): 0 false NO-BID; every FAIL names a gate and a fact |
| R1-3 | **Export binds to content.** Approvals store a content hash; any edit, reuse-accept or regenerate invalidates approvals whose hash no longer matches; save revalidates flags (`validate_draft`) instead of clearing them; unverified non-financial claims in narrative block export unless attested; attest/attach/delete controls exist on the proposal page (S9-D1..D3 selectors) | `export_gate.py`, `db.py:1004,281`, `proposal_routes.py`, `ProposalDocument.tsx`, migration | L | Integration: edit after approval → export 409; attest → 200; viewer 403 (done) |
| R1-4 | **One blocker list.** `submission_state` passes `export_gate.decide().hard_blockers`; DOCX button reads the same decision; "Export final documents" returns the file (or is renamed "Mark as submitted") | `readiness_routes.py:161`, `SubmissionMeter.tsx`, `ProposalDocument.tsx:240`, `ExportGate.tsx:85` | S–M | `can_submit` true ⇔ DOCX 200 |
| R1-5 | **Read the whole package before "ready".** Lock/readiness carry `pages_unread` (illegible minus recovered, over the OCR budget); a tender with unread pages is "Ready with N pages unread", never plain ready; unmapped requirement sentences from the matrix feed the same list | `deterministic/lock.py`, `tenders.py:279-443`, `readiness.py` | M | Readiness on the Oil India package names its 17 unread pages |

### R2 — Discovery that ranks (2 weeks, parallelisable with R1) → M16 · satisfies G5

| Task | Change | Files | Effort | Done when |
|---|---|---|---|---|
| R2-1 | Server-side: exclude closed by default (keep `closing_at is null`), order by composite, cursor pagination on `(score, id)`, search by reference/title | `db.py:1429`, `opportunities_routes.py:51`, `OpportunityFeed.tsx:440-470` | M | A known reference is findable; no closed row on page one |
| R2-2 | **Composite score with reasons.** Store model `confidence`; copy `estimated_value_inr` to the column; add deterministic comparators for EMD affordability, experience years, and certifications from the parsed bid document; score = f(band confidence, category hit, eligibility margin, value-in-band, runway); `reasons[]` and one `risk` per row. PRD F-FR11 amended by the owner to allow a number | `pipeline/relevance.py:122`, `discovery/relevance.py`, `deterministic/discovery.py`, `ingest.py:525`, migration, PRD | M | Feed shows a score and ≤3 reasons; partner rating ≥60% "worth a look" on the top 25 |
| R2-3 | **Pursue fetches and starts.** On pursue: fetch `document_urls` through the guarded fetcher (G-10), ingest as a package, link pursuit, kick the R3 chain; pursuits list page with stage | `opportunities_routes.py:287`, `tenders.py`, new `/pursuits` page | M | Pursue → readiness with no upload for a GeM tender |
| R2-4 | Merge GeM ⇄ BidAssist duplicates on `overlaps_source` + normalised ref; per-source freshness in the header (oldest wins) | `ingest.py`, `db.py:1619` | S–M | One row per tender across sources |
| R2-5 | Rules UI (keyword, category prefix, value band, authority, min days) and the GeM category editor; refresh reports per-source result | `OpportunityFeed.tsx`, `/prices`, new web handlers for `/rules`, `/categories` | M | A customer can add and remove a rule without an API call |

### R3 — The right document, automatically (3–4 weeks) → M17 · satisfies G6

| Task | Change | Files | Effort | Done when |
|---|---|---|---|---|
| R3-1 | **Jobs table + chain.** Upload → extract → classify → auto-confirm when no low-confidence gates → prepare → draft, as durable background jobs with real stage events (replaces `BackgroundTasks` and the timer progress) | new `jobs` table + worker loop in engine, `tenders.py`, `StageProgress.tsx` | L | A clean package reaches a draft with zero clicks; `StageProgress` reflects job events |
| R3-2 | **Tender-derived outline.** Sections = the tender's named forms/annexures/evaluation heads (from `kind=form` items and headings) + for goods a per-line technical compliance table from `spec_match`; `SECTION_SPECS` only as the fallback when the tender names none; per-criterion responses become the requirement-by-requirement response section instead of a "Comply" label | `sections.py`, `proposal_routes.py:86-198`, `spec_service.py`, `ProposalDocument.tsx` | L | The UML package produces a cover letter, PQ sheet, item-wise compliance table, deviations, declarations — and no SLA section |
| R3-3 | **One requirement record.** Readiness item, matrix row, in-document compliance row and export blocker read one `requirements` view with linked response, evidence, owner, decision; retire the other two matrices and six coverage numbers | `deterministic/matrix.py`, `export_service.py`, `readiness.py`, `submission.py`, `MatrixWorkspace.tsx`, `ExportGate.tsx` | L | A decision in one view shows in all |
| R3-4 | **Retain and read source documents.** Store uploads in `DOCUMENTS_BUCKET`; page viewer beside each requirement (S4's source pane, finally); library ingestion gets OCR and DOCX tables through the same parser as tenders; drop the 20k-char truncation in favour of chunked retrieval | `tenders.py`, `knowledge.py:33-78`, `retrieval.py`, new viewer component | L | A citation opens the page it cites; a table-only turnover DOCX yields its figures |
| R3-5 | **Reuse during generation.** Prior answers and confirmed facts are offered inline as proposed completions, accepted per item; harvest remains approval-gated | `reuse_routes.py`, `section_drafter.py`, `ProposalDocument.tsx` | M | Reuse acceptance ≥40% on second tender in a workspace (PH4e gate) |
| R3-6 | Approve-all; solo-bidder mode (one member → one approval); `approvals_required` written from workspace size | `export_gate.py:99-121`, `proposal_routes.py`, `ProposalDocument.tsx` | S | Solo writer exports in ≤ 8 clicks |

### R4 — A stranger can start (2 weeks) → M18 · satisfies G4

| Task | Change | Files | Effort | Done when |
|---|---|---|---|---|
| R4-1 | Signup + password recovery; invite accepts without a prior account (creates it) | `(auth)/`, `AcceptInvite.tsx`, `members_routes.py` | M | `/verify` as a fresh email |
| R4-2 | **Company setup from evidence.** Website + 3 uploads (incorporation/GST, latest CA turnover certificate, ISO certs) → proposed facts with citations (`structured_fields` already exists) → confirm → keywords suggested → first shortlist; one "Your company" screen replaces the split across profile/capability/library; every field editable | `knowledge_routes.py`, `spec_service.py`, `ProfileForm.tsx`, `CapabilityEditor.tsx`, dashboard empty state | L | ≥70% of profile fields pre-filled from uploads on the UML documents |
| R4-3 | Inbound email creates workspace-private opportunities from GeM alerts; bid-actions inbox with done-state; profile save re-runs affected analyses | `inbound_routes.py:157`, new `/inbox` panel, `analyze_routes.py:191` | M | A forwarded GeM alert appears in the feed within a minute |
| R4-4 | Dashboard: active pursuits by deadline and open blocking action (not latest 20); remove hardcoded "Unlimited"; settings loses static chains/thresholds | `dashboard/page.tsx:57-98`, `settings/page.tsx` | S | |

### R5 — Submission package and measurement (after R3) → M19

| Task | Change | Effort |
|---|---|---|
| R5-1 | Package builder: response DOCX/PDF + attachment manifest (evidence files with validity dates, prescribed forms, signature checklist, priced BOQ, portal field mapping); "attached/enclosed" only when the manifest holds the file | XL |
| R5-2 | Corrigendum import: diff criteria, invalidate affected responses and approvals, re-verify | L |
| R5-3 | Outcome telemetry: relevant/irrelevant reasons on the feed, bid/no-bid decision, submission, result — feeds G2/G5 golden sets and finally un-suppresses the estimator honestly | M |

---

## 4. Sequencing and parallelism

```
week 1     R0 (all)  ───────────────────────────────┐
weeks 2–4  R1-1 → R1-2 → R1-3 → R1-4/R1-5          │  engineer A
weeks 2–3  R2-1 → R2-2 → R2-3 → R2-4/R2-5          │  engineer B (independent of R1)
weeks 5–8  R3-1 → R3-2 → R3-3 → R3-4 → R3-5/R3-6   │  both
weeks 9–10 R4                                       │
after      R5                                       │
```

R1 and R2 do not touch the same files and can run in parallel. R3 depends on R1-1 (classification) and R1-3 (content-bound approvals). R4-2 depends on R3-4 (retained documents + parser). Ship UML the R0 + R1 + R2 build; it fixes what they see today (false NO-BID, dead deadlines, seventy-two equals). A second customer needs R3 + R4.

Each task follows the repo's definition of done: typecheck/lint/tests, `/verify` or `/verify-api` on touched surfaces, `/evals` for any prompt or extractor change, `/review` on every `complexity: high` item (R1-2, R1-3, R3-1, R3-3 are all high).

---

## 5. Decisions the owner must make

1. **PRD F-FR11**: allow a numeric relevance score with reasons (R2-2). Both audits want it; the PRD forbids it today.
2. **Which sections may a viewer, writer, reviewer approve**: today's fix gates section approval on `draft`; confirm that is the intended signature role.
3. **Test account placement**: FIX-1 currently operates inside Usha Martin's workspace. Move to a demo workspace (recommended) or keep for demos and document it.
4. **Deadline backfill and mail env** are production writes: approve R0-7.
5. **Codex §D residue**: D1–D4 are settled above; nothing else in the outside review is disputed.
6. **Scope for UML's next demo**: R0 + R1 + R2, or R0 + R1 only. R2 is what changes their daily screen.

---

## 6. How we will know it worked

| Metric | Today (measured 2026-09-15) | Target after R2 | After R4 |
|---|---|---|---|
| Rows shown "high" in the UML feed | 72 (all rows) | ≤ 25 scored, ordered | — |
| False NO-BID on in-scope partner tenders | 1 of 1 examined | 0 of 20 labelled | 0 |
| Items awaiting verification per tender | ~150 (896 / 6) | ≤ 15 (gates only) | ≤ 10 |
| Clicks upload → DOCX, solo writer | 23 + k + m, two people | — | ≤ 8, one person |
| Pre-drafted share of a usable goods proposal | ~10–15% | — | ≥ 60% |
| Profile fields typed by hand | all | — | ≤ 30% |
| Tenders with a recorded deadline | 0 of 6 | 6 of 6 | all |
| Unsupported statements about the bidder in an export | 3 found | 0 | 0 |
