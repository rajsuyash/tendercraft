# Codex product audit — the bidder product, end to end

**Status:** received, unactioned · **Produced:** 2026-09-15 · **Reviewer:** OpenAI Codex
(codex-cli 0.154.0, read-only sandbox, ~4.75M tokens) via `/codex` consult mode
**Decision owner:** human sign-off required before any P0 in §10 is scheduled
**Scope:** `apps/web` + `services/engine` only. The evaluate product and its engine were
excluded by the prompt (F13 wall), as were the connector internals.

## Why this file exists

`docs/feedback/` records what a *customer* said. This is the first entry in `docs/reviews/`,
which records what an *outside reviewer* said — a different thing, and worth keeping separate:
a customer's words are evidence about the market, a reviewer's are a claim about the code that
can be checked and can be wrong. The brief asked one question of every feature: does this make
it easier for the customer to find the right tender and win it?

The audit is reproduced **verbatim** below, including the parts this repo disagrees with. Two
sections follow it:

- **§V — what was independently verified**, because an agent's "reproduced" is its own probe,
  not this codebase's test suite, and two of these findings were checked by hand before the
  report was accepted.
- **§D — what is disputed or needs a second look**, because a finding accepted uncritically is
  how a correct behaviour gets "fixed".

Nothing here has been actioned. No code changed as a result of this audit. The one A4 fix
committed the same day (`10d1a99`) predates it and is unrelated.

---

# 1. Executive summary

**TenderCraft helps assemble tender work, but it does not reliably deliver either outcome end to end.**

- **Finding relevant tenders:** matching exists, but the customer sees a capped, partially evaluated feed without effective search or complete company-fit assessment. Relevant opportunities can remain unreachable.
- **Producing submission-ready proposals:** drafting exists, but completeness, eligibility, approval and export use different definitions of “ready.” Some unsupported claims can pass export.
- **Reducing effort:** users still download and re-upload documents, enter company facts separately from their evidence, confirm extractions without viewing the source, rerun matching, and manually assemble submission attachments.
- **Serving the actual customer:** the proposal generator imposes an IT-services structure on a product whose only documented design partner sells manufactured wire rope.

**Keep:** requirement extraction, explicit gaps, explained relevance bands, evidence reuse, schedule-to-capability comparison and clarification tracking. These contribute directly to the two outcomes.

**Fix before expanding:** misleading qualification/compliance signals, incomplete-document handling, the discovery-to-pursuit handoff, feed reach and the final submission package.

### Evidence standard

- **Traced:** followed repository UI, Next.js handlers, engine functions and database definitions. This establishes implemented behavior, not production deployment.
- **Reproduced:** executed isolated probes against actual functions or FastAPI routes, with database/model operations replaced in memory.
- **Unverified:** live corpus quality, deployed migrations, scheduler operation, browser appearance and production latency.

**Validation:** 81 existing analysis/readiness/submission/export/lock tests passed. Additional probes reproduced failures described below. No files changed; no live writes or model calls.

---

# 2. Current user journey

| Stage | Actually implemented | Customer consequence |
|---|---|---|
| Sign up | `/login` supports password sign-in. “Start free” is plain text. Invitation acceptance expects an existing signed-in account. | A new customer cannot complete self-service onboarding. |
| Describe company | `/profile` collects capability text, keywords, financials, certifications and projects. `/library` separately collects evidence. `/capability` holds manufacturing specifications. | The customer must understand three representations of their company. |
| Discover | `/opportunities` → `engineFetch()` → `GET /api/opportunities` → `db.get_feed()` → `opportunity_matches` joined to `opportunities`. | Explained bands exist, but only 100 records reach the page; subsequent sorting/filtering is local. |
| Select an opportunity | “Pursue” → Next proxy → engine `pursue()` → `pursuits`; redirects to `/tenders/upload?pursuit=…`. | The customer still downloads documents themselves. |
| Upload | Multipart upload → `/api/tenders/ingest` → `_process_ingest()` → criteria, unmapped sentences and schedule rows. OCR runs afterwards. | The pursuit identifier is lost at the multipart boundary. Original documents are not retained. |
| Decide bid/no-bid | `/tenders/:id/readiness` → `/prepare` → lock → eligibility analysis → per-criterion drafting. | A bid decision is coupled to drafting every requirement. |
| Generate proposal | `/proposals/:tenderId` → `/sections/generate` → fixed section specifications → `proposal_sections`. | Every tender receives the same 17-section IT-services structure. |
| Resolve gaps | Upload evidence against a requirement, edit the profile, re-match, accept reused answers, edit Markdown sections. | Several actions repeat work; editing the final document does not resolve the separate criterion-response record. |
| Approve | Individual narrative approvals plus proposal-level approval stages. | Approval validity is not consistently tied to the exact document version. |
| Export/submit | “Export final documents” records export state. A separate DOCX endpoint downloads the document. | No complete submission pack; export confirmation and downloading are disconnected. |

Relevant entry points: [login:17](<apps/web/app/(auth)/login/page.tsx:17>), [opportunities page:32](<apps/web/app/(app)/opportunities/page.tsx:32>), [prepare:120](<services/engine/app/readiness_routes.py:120>), [proposal generation:86](<services/engine/app/proposal_routes.py:86>).

---

# 3. Critical problems

## C1 — P0: Eligibility confidence exceeds the evidence

**Customer impact:** pursue an ineligible bid, or treat an unverified exemption as permission to proceed.

In `analysis.decide()`:

- Numeric comparisons use **both required and actual values supplied by the model**.
- That numeric branch bypasses the confidence/evidence check.
- Other checks fall back to the model’s proposed verdict.
- `exemption_applies=True` waives a failure without requiring a valid exemption clause.
- Evidence IDs are checked for presence, not resolved against actual profile records.

**Reproduced:**

- Numeric evaluation with confidence `0.01` and no evidence → `pass`.
- Failed turnover check with `exemption_applies=True` and no exemption clause → exemption granted.

The deterministic comparison is real; the facts being compared are not independently established.

**Change:** extract typed requirements, bind actual values to verified company facts, calculate financial-year windows and exemptions deterministically, and leave unresolved facts as “needs review.”

**Effort:** L.  
**Files:** [analysis.py:55](<services/engine/app/analysis.py:55>), [pipeline/analyzer.py:65](<services/engine/pipeline/analyzer.py:65>).

## C2 — P0: Export does not consistently enforce the claims in the document

**Customer impact:** download a proposal containing unsupported claims or material that was never approved in its current form.

Three separate defects:

1. **An unverified nonfinancial claim in a long-form section does not block export.** Section checks cover financial flags, placeholders and unapproved narrative sentences, but omit general unverified section claims. Reproduced `exportable=True`.
2. **Saving a section clears all flags and marks it drafted without revalidation.** Saving identical text containing an unsupported financial amount produces that patch.
3. **Regeneration overwrites section content without explicitly clearing previous approvals.** The database upsert preserves fields it does not replace; no corresponding invalidation trigger appears in the migrations. Manual edits clear section approval but retain proposal-level approvals.

Additionally, **a viewer can approve a section**: the endpoint checks proposal ownership but not approval permission. Reproduced HTTP 200 with a viewer identity and mocked persistence.

**Change:** validate the exact export text; bind approvals to document/content versions; invalidate affected approvals on every edit, reuse and regeneration; enforce roles at every mutation.

**Effort:** L.  
**Files:** [export_gate.py:88](<services/engine/app/deterministic/export_gate.py:88>), [db.py:1004](<services/engine/app/db.py:1004>), [section upsert:281](<services/engine/app/db.py:281>), [section approval:327](<services/engine/app/proposal_routes.py:327>).

## C3 — P0: “Ready” does not mean the tender was fully read or answered

**Customer impact:** omitted obligations remain invisible while the interface signals completion.

- Submission readiness does not consume the export gate’s complete blocker list.
- The standalone matrix checks unmapped requirements; proposal export does not load that unmapped set.
- Locking checks existing criteria, not unread pages or pending OCR.
- OCR can add criteria after the initial lock/analysis.
- OCR defaults to a 60-page budget. Completion records recovered pages, not a complete inventory of unresolved pages.
- Requirement-denominator detection relies on obligation keywords and minimum sentence length.

**Reproduced:** readiness returned **100%, `can_submit=True`** while export rejected a mandatory placeholder.

Also reproduced: “Submission of Form 3 is a precondition for participation” yielded **zero detected requirement sentences**.

**Change:** one readiness evaluator over document processing, requirements, evidence, responses and approvals. Track every page; prohibit a final-ready state while any required document is unread or any obligation unresolved.

**Effort:** L–XL.  
**Files:** [readiness_routes.py:150](<services/engine/app/readiness_routes.py:150>), [matrix_routes.py:107](<services/engine/app/matrix_routes.py:107>), [lock.py:18](<services/engine/app/deterministic/lock.py:18>), [shred.py:120](<services/engine/app/deterministic/shred.py:120>), [OCR processing:279](<services/engine/app/tenders.py:279>).

## C4 — P0: The product manufactures compliance conclusions

**Customer impact:** submit an incorrect declaration or abandon a bid because of invented evaluation rules.

- `assemble_deviations()` writes **“The bidder confirms no deviations”** without consulting schedule mismatches or clarification answers.
- `assemble_compliance_matrix()` translates `drafted` into **“Comply.”** Having generated prose does not establish compliance.
- The technical rubric applies fixed weights, three-project/three-CV expectations and 45%/65% thresholds. The UI says **“Technically disqualified.”**
- Word count, headings and approval state contribute to this supposed technical competence score. They do not measure whether an evaluator will accept the solution.

**Change:** remove automatic no-deviation declarations and qualification verdicts based on generic rubrics immediately. Use tender-specific evaluation criteria; label generic writing checks as editorial checks.

**Effort:** S to remove misleading output; L for tender-specific evaluation.  
**Files:** [sections.py:249](<services/engine/app/sections.py:249>), [rubric.py:28](<services/engine/app/deterministic/rubric.py:28>), [rubric_service.py:79](<services/engine/app/rubric_service.py:79>), [RubricCard.tsx:106](<apps/web/components/RubricCard.tsx:106>).

## C5 — P1: Discovery can hide the opportunity the customer needs

**Customer impact:** miss a bid without receiving an error.

The page requests 100 records. `get_feed()` limits before the browser removes closed records or sorts by deadline/value. There is no pagination or search in this path.

Consequences:

- “Closing soonest” means soonest **inside the fetched subset**.
- Closed, highly ranked records can consume display capacity.
- Counts can describe opportunities the customer cannot reach.
- A user cannot directly find a known reference to check whether coverage is working.

The recent recomputation paging fix addresses the matching corpus, **not this display limit**.

**Change:** server-side open/closed filters, complete sorting, cursor pagination and search; show a small recommended shortlist with access to the full corpus.

**Effort:** M.  
**Files:** [get_feed:1429](<services/engine/app/db.py:1429>), [OpportunityFeed.tsx:440](<apps/web/components/OpportunityFeed.tsx:440>).

---

# 4. Broken features — with root cause

| ID / priority | Failure and root cause | Recommended fix / effort |
|---|---|---|
| **B1 · P1** | **Pursuit handoff loses context.** Browser appends `pursuit_id` and `title` to multipart data; engine declares them as query parameters. Actual-router probe returned `pursuit_id=""`. The discovery link and metadata fallback never execute. | Use `Form()` fields; add a multipart contract test. **S** |
| **B2 · P1** | **“Export final documents” downloads nothing.** POST `/export` writes status/audit/learning records and returns JSON. DOCX download is a separate GET that does not perform the same export-state transition. | One explicit package-generation/download flow with a recorded artifact version. **M** |
| **B3 · P1** | **Download can still lead to a raw error.** The proposal enables its DOCX link when narrative sections are approved, ignoring mandatory response blockers and proposal-level approvals. | Drive the button from the actual export decision; render errors in place. **S** |
| **B4 · P1** | **Verification can dead-end.** `VerifyQueue` requires a clause number; engine locking accepts a page-only anchor. The UI offers confirmation but no anchor correction. | Share the lock contract and provide source-backed correction. **S–M** |
| **B5 · P1** | **Evidence ingestion loses important content.** Library PDF ingestion has no OCR. DOCX extraction reads paragraphs but not tables; a table-only financial document reproduced empty text. Tender/past-bid upload rejects DOCX. | One document parser supporting tables, OCR and common package formats. **M–L** |
| **B6 · P1** | **Email workflow stops before the customer.** Inbound emails are stored; bid-alert emails create no opportunity. Clarification actions have a GET endpoint, but no bidder-web consumer was found. | Create workspace-private opportunities from alerts; show an actionable inbox with completion state. **M** |
| **B7 · P1** | **Uploaded tender deadlines are not extracted into structured metadata.** The metadata write stores reference and authority. The intended discovery fallback is additionally broken by B1. | Extract and confirm all key dates; retain their document anchors. **M** |
| **B8 · P1** | **Final document uses “Bidder” on the cover.** DOCX export reads `tender.bidder_name`, while the actual registered name lives in the profile. | Use confirmed legal identity consistently. **S** |
| **B9 · P2** | **Turnover summary cannot use the required year window.** The assembler accepts `required_fys`, but generation never supplies it; it emits “Required FY window not confirmed.” | Bind confirmed financial requirements to the assembler. **S–M** |
| **B10 · P2** | **Refresh failure is invisible.** Feed refresh awaits `fetch()` but ignores HTTP status and response-level source failures. | Show source-specific result, failure and last successful coverage. **S** |

Evidence: [B1 browser:71](<apps/web/app/(app)/tenders/upload/page.tsx:71>) / [engine:446](<services/engine/app/tenders.py:446>); [B2:418](<services/engine/app/proposal_routes.py:418>); [B3:238](<apps/web/components/ProposalDocument.tsx:238>); [B4:49](<apps/web/components/VerifyQueue.tsx:49>); [B5:33](<services/engine/app/knowledge.py:33>); [B6:157](<services/engine/app/inbound_routes.py:157>); [B7:958](<services/engine/app/db.py:958>); [B8:389](<services/engine/app/proposal_routes.py:389>); [B9 caller:122](<services/engine/app/proposal_routes.py:122>); [B10:584](<apps/web/components/OpportunityFeed.tsx:584>).

---

# 5. UX friction

### P1 — No coherent first-run setup

The dashboard offers discovery before establishing whether the company has enough information to receive useful matches. The user must discover profile, library and capability setup themselves.

**Change:** company website plus document upload → proposed company facts → confirmation → first shortlist. Ask only for missing preferences and unverifiable facts. **Effort: M–L.**

### P1 — Mobile/tablet navigation disappears

The sidebar is `hidden … lg:flex`; the app shell supplies no replacement navigation.

**Change:** compact navigation with workspace switching below desktop width. **Effort: S–M.**

[Sidebar.tsx:76](<apps/web/components/design/Sidebar.tsx:76>)

### P1 — Verification asks users to approve the extraction itself

The verification screen displays extracted text and an anchor label, not the original page beside it. Users must open their own copy and locate the clause. They cannot correct the extraction there.

**Change:** retained source page, highlighted passage, editable requirement fields and a focused review queue. **Effort: L.**

### P1 — Fixing company data requires repeated manual work

An uploaded certificate or financial statement becomes a library document. It does not populate the structured profile used by eligibility. Profile save does not automatically reanalyze affected bids.

**Change:** propose verified facts from uploads; identify conflicts; confirm once; automatically refresh affected assessments. **Effort: L.**

[knowledge_routes.py:20](<services/engine/app/knowledge_routes.py:20>), [profile update:191](<services/engine/app/analyze_routes.py:191>)

### P2 — Too many representations of the same work

Readiness checklist, standalone matrix, generated compliance table and export matrix are separate views with separate stored states. A correction in one does not necessarily resolve another.

**Change:** one requirement record with linked response, evidence, owner and blocker state; multiple views over it. **Effort: L.**

### P2 — Progress implies events the system has not observed

`StageProgress` advances on elapsed time and renders checkmarks against preceding stages. It does not receive processing events.

**Change:** show elapsed time honestly until durable jobs provide actual stage progress. **Effort: S now; L for jobs.**

[StageProgress.tsx:33](<apps/web/components/StageProgress.tsx:33>)

### P2 — Dashboard urgency is incomplete

It fetches the latest 20 tenders, then sorts those by deadline. An older urgent tender can be absent. “Active tenders” counts all tenders.

**Change:** query active pursuits by deadline and unresolved blocking action. **Effort: S–M.**

[dashboard/page.tsx:57](<apps/web/app/(app)/dashboard/page.tsx:57>)

---

# 6. Tender discovery assessment

**Verdict: useful matching signals; inadequate opportunity coverage and decision support.**

| Dimension | Assessment |
|---|---|
| Industry/product fit | Capability statement and keywords influence ranking. Recent code also derives terms from registered categories and manufacturing standards. |
| Geography | Geography is stored, but the inspected relevance model does not use it. Country selection is not delivery/service-area matching. |
| Value | Stored, but not part of semantic relevance. UI value sorting uses enriched eligibility values rather than the normalized value field. |
| Certifications/experience | Not assessed by the relevance scorer. |
| Manufacturing capability | Standard names feed keywords; detailed parameter comparison happens later on the schedule screen. |
| Deadline | Used for ordering and processing budgets, not an assessment of whether the customer has enough preparation time. |
| Explanation | High/medium/low bands have rationale and distinguish keyword fallback. This is preferable to an unsupported percentage. |
| Preliminary eligibility | Turnover-focused. Profile turnover averages all stored years, rather than the tender’s specified window. |
| Search/filtering | No end-user query, geography filter, value filter or pagination in the feed path inspected. |
| Duplicates | Upsert identity is `(source_id, portal_ref_no)`. This prevents same-source repetition but preserves cross-source duplicates; no cross-source grouping appears in the feed. |
| Freshness | Scheduler entry points exist. Display freshness comes from recently seen opportunity rows by market, not a per-source successful-run/coverage record. One working Indian source can conceal another failing one. |
| Unknown information | Missing turnover renders **“none stated”** even when the document has not been read. Unknown is being presented as absence of a requirement. |

Sources: [capability terms:282](<services/engine/app/discovery/ingest.py:282>), [relevance input:54](<services/engine/pipeline/relevance.py:54>), [turnover calculation:360](<services/engine/app/discovery/ingest.py:360>), [deduplication:1201](<services/engine/app/db.py:1201>), [freshness:1619](<services/engine/app/db.py:1619>), [“none stated”:1037](<apps/web/components/OpportunityFeed.tsx:1037>).

### Does the customer still scan hundreds of tenders?

**The implementation does not establish that this burden has been removed.** It presents a table of up to 100 records, rather than a validated daily shortlist.

The PRD targets ≥95% historical recall, ≥60% “worth a look” precision and ≤25 in-scope opportunities per day. Those are targets, not results established by this audit.

**Next investment:** partner-labelled relevance evaluation, complete searchable access, explicit unknowns and a daily shortlist with concise reasons. More connectors alone will increase noise.

---

# 7. Proposal creation assessment

**Verdict: generates substantial text; does not reliably assemble a complete, tender-specific submission.**

### Requirement extraction and bid/no-bid

Categories, requirement levels, evidence instructions and evaluation weights are extracted. But:

- Per-page extraction has limited cross-page context.
- The readable-page heuristic is character count, not measured word accuracy.
- The review interface cannot correct core requirement fields.
- The displayed “weighted score” is an unweighted pass fraction over nonmandatory criteria.
- No consolidated, source-backed decision brief brings together scope, dates, commercial exposure, mandatory documents, manufacturing gaps and disqualification risks.

[analysis.py:91](<services/engine/app/analysis.py:91>)

### Drafting and reuse

Implemented:

- Per-requirement evidence retrieval and drafting.
- Explicit placeholders.
- Accepted-answer reuse with provenance and stale-claim checks.
- Structured company tables.
- Section editing.

Weaknesses:

- Retrieval is lexical overlap, not the hybrid semantic retrieval described in the PRD.
- Library text is truncated to 20,000 characters.
- Structured facts extracted into library metadata are not the common fact source for eligibility and drafting.
- Long-form narratives are independently generated; there is no comprehensive cross-section contradiction check.
- Reuse is a separate interaction rather than a proposed, reviewable completion of the whole response.

[retrieval.py:98](<services/engine/pipeline/retrieval.py:98>), [knowledge.py:210](<services/engine/app/knowledge.py:210>), [reuse_routes.py:101](<services/engine/app/reuse_routes.py:101>)

### Citation quality

A citation passes when its ID belongs to the retrieved set. That proves the reference exists; it does not prove the passage supports the claim.

Long-form `body_md` is assembled from sentence text without rendering the structured citation references. The review page does not provide the promised claim-to-source inspection experience.

[drafting.py:175](<services/engine/app/deterministic/drafting.py:175>), [section_drafter.py:154](<services/engine/pipeline/section_drafter.py:154>)

### Submission package

The exporter creates a DOCX from section text. It does not assemble original evidence files, prescribed forms, signed declarations or a priced BOQ.

Some generated sections nevertheless say CVs are “attached.” Original uploaded files are not retained, so that assertion cannot be satisfied by this exporter.

No bidder PDF-export or portal-field mapping implementation was found in the inspected routes.

**Highest-impact change:** derive the response structure from the actual tender and generate an attachment manifest with verified files, signatures, validity dates and destination fields.

[sections.py:229](<services/engine/app/sections.py:229>), [docx_export.py:217](<services/engine/app/docx_export.py:217>), [source retention limitation:344](<services/engine/app/tenders.py:344>)

---

# 8. Features to remove or simplify

| Priority | Feature | Decision |
|---|---|---|
| **P0** | Generic “Technically disqualified” verdict | Remove until grounded in this tender’s evaluation rules. |
| **P0** | Automatic “no deviations” statement | Replace with an explicit, evidence-backed owner decision. |
| **P1** | Universal 17-section proposal | Replace with tender-derived response sections. Offer a services template only when appropriate. |
| **P1** | Four separate compliance/readiness representations | Consolidate their underlying state and blocker calculation. |
| **P2** | Standalone Learning destination | Move useful reuse suggestions into drafting; retain diagnostics behind a secondary view. |
| **P2** | Manual style rebuild/recompute operations | Run automatically when inputs change; ask users to approve consequential changes, not initiate bookkeeping. |
| **P2** | Generic estimated marks and threshold likelihood | Suppress until validated against actual outcomes and the relevant tender rubric. |
| **P2** | Separate full analysis before every draft refresh | Recompute affected requirements only. |

The estimator explicitly describes itself as a heuristic, with fixed expected mark gains. More recorded outcomes narrow its interval even without measured accuracy. That is not a basis for investment decisions.

[estimator.py:32](<services/engine/app/estimator.py:32>)

---

# 9. Missing features

Only additions that materially advance discovery or submission:

1. **P1 — Company setup from evidence.** Website and uploads propose company facts, products, regions, financials and credentials; users confirm conflicts. **Effort: L.**
2. **P1 — Complete, searchable discovery with a daily shortlist.** Explain fit, uncertainty, urgency and missing qualifications. **Effort: M–L.**
3. **P1 — One-page bid decision brief.** Scope, eligibility, dates, required documents, effort, EMD/security exposure, gaps and reasons to proceed or stop. **Effort: L.**
4. **P1 — Source document retention and review.** Original files, page viewer, stable citations and recoverable processing. **Effort: L.**
5. **P1 — Unified missing-information workflow.** Search existing facts and evidence first; ask the smallest outstanding question; assign it once. **Effort: L.**
6. **P1 — Submission package builder.** Tender-specific forms, evidence attachments, BOQ, signatures, file naming and export manifest. **Effort: XL.**
7. **P1 — Corrigendum impact tracking.** Import changed documents, show affected requirements, invalidate stale responses and approvals. No complete workflow was found. **Effort: L.**
8. **P2 — Partner feedback tied to outcomes.** Relevant/irrelevant reasons, bid/no-bid decisions, submission effort and rejection reasons. **Effort: M.**

For UML, schedule fit, catalogue status, clarifications and item-level price evidence should lead the workspace. Historical prices exist, but the licensed award extension remains gated in the registry; this audit did not establish five-year coverage. Do not treat the opportunity feed and award-data gate as the same thing.

[registry.py:80](<services/engine/app/discovery/registry.py:80>)

---

# 10. Prioritised roadmap

*Effort is relative engineering scope, not a calendar estimate.*

| Priority | Problem | Customer impact | Proposed change | Engineering effort | Recommendation |
|---|---|---|---|---|---|
| **P0** | C1: unsafe eligibility facts/exemptions | Wrong bid decision | Bind comparisons to verified facts and cited requirements | L | First release gate |
| **P0** | C2: export validation and stale approvals | Unsupported submission | Validate final text; version approvals; enforce roles | L | First release gate |
| **P0** | C3: incomplete processing can appear ready | Missing mandatory obligations | Unified blocker evaluator including OCR/unmapped work | L–XL | First release gate |
| **P0** | C4: invented compliance/qualification | False declarations or abandoned bids | Remove misleading outputs; require explicit decisions | S initially | Immediate containment |
| **P1** | C5: capped discovery | Missed opportunities | Server filtering/sorting, search and pagination | M | Next |
| **P1** | B1/B7: broken pursuit and dates | Re-entry, lost provenance/deadlines | Correct multipart binding and structured date extraction | S–M | Immediate |
| **P1** | No self-service onboarding | Cannot start using product | Signup/recovery plus company setup | M–L | Before broader acquisition |
| **P1** | B5: incomplete evidence ingestion | Library cannot answer requirements | Common OCR/table/document pipeline with retained files | L | Foundation |
| **P1** | Fixed proposal structure | Irrelevant output and editing burden | Tender-derived outline and prescribed forms | L | Core product work |
| **P1** | B2/B3: fragmented export | “Exported” without usable deliverable | One versioned package/download workflow | M, then XL | Fix semantics first |
| **P1** | B6: invisible inbound work | Missed leads/document requests | Private alert ingestion and actionable inbox | M | Complete existing feature |
| **P1** | Disconnected company facts | Repeated entry and stale verdicts | Confirmed facts shared across profile, evidence and bids | L | Core automation |
| **P1** | Missing responsive navigation | Cannot navigate on smaller devices | Responsive app shell | S–M | Quick release |
| **P2** | Repeated re-match/regeneration | Time, cost and lost edits | Incremental jobs and selective regeneration | L | After correctness |
| **P2** | Unmeasured relevance/effort savings | Cannot establish product value | Partner-labelled evaluation and outcome telemetry | M | Start measurement now |
| **P3** | More cosmetic analytics/templates | Little direct outcome improvement | Defer | — | Do not prioritise |

---

# 11. Quick wins

1. Bind upload `title` and `pursuit_id` with `Form()`.
2. Remove the default no-deviation declaration.
3. Replace generic technical disqualification language with clearly labelled editorial checks.
4. Add the missing permission check to section approval.
5. Block unverified long-form claims at export.
6. Align page-only anchor handling between verification and engine.
7. Replace “none stated” with “not checked” when document eligibility is absent.
8. Use the profile’s legal name on the DOCX cover.
9. Make “Export final documents” actually deliver a file, or rename it accurately.
10. Surface refresh failures and provide responsive navigation.

These are bounded corrections. They do not replace the deeper work on document completeness, approved versions and submission packaging.

---

# 12. Ideal future experience

1. **Tell us who you are.** Enter a website and upload company documents. Confirm the facts the system extracted.
2. **Review a short daily list.** Each tender explains why it fits, what is uncertain and when action is required. Search the complete corpus at any time.
3. **Open one decision brief.** Understand scope, qualification, risks, required effort and missing evidence before committing.
4. **Choose “Prepare bid.”** Public documents are imported automatically where permitted; upload only inaccessible material.
5. **Resolve exceptions.** The system reuses confirmed facts and prior answers, then asks only unanswered questions.
6. **Review the actual submission.** Tender-specific responses, prescribed forms and evidence sit beside their sources. Changes invalidate affected approvals.
7. **Download one checked package.** It contains the response, attachments, BOQ/forms, signature checklist and portal instructions. Record submission afterwards.

**The product should make the customer decide and approve. It should do the finding, reading, assembling, checking and bookkeeping itself.**


---

# §V — What was independently verified

Everything above is the reviewer's own tracing and its own in-memory probes. Two findings were
re-checked by hand before this file was written, chosen because they are the cheapest to act on
and the most expensive to get wrong. Both **confirmed**.

### B1 — the upload's `title` and `pursuit_id` never arrive. CONFIRMED.

`services/engine/app/tenders.py` declares them as bare `str` defaults on `ingest_tender`:

```python
file: Annotated[list[UploadFile], File()], title: str = "", pursuit_id: str = "",
```

FastAPI binds a bare `str` default as a **query** parameter. `apps/web/app/(app)/tenders/upload/page.tsx:73-80`
sends both as **multipart form fields** (`form.append("title", …)`, `form.append("pursuit_id", …)`),
and `apps/web/app/api/tenders/ingest/route.ts` is a straight multipart passthrough. So both are
empty on every upload that has ever run.

Two consequences, and the second is the one worth noticing:

1. `_apply_pursuit_context` never fires — the discovery → pursuit → tender link is dead, and the
   portal's reference, authority and closing date never fill the document's gaps.
2. `name = title or documents[0][0] or PLACEHOLDER_TITLE` falls straight to the **filename**.
   That is the exact symptom the 2026-09-14 plan's task B3 spent a task fixing downstream
   (`display_title`, `_NOISY_FILENAME`, the rename affordance, a backfill migration) — while the
   parameter that was supposed to carry a real name never arrived at all. **A downstream fallback
   was hardened against a value that a binding bug guaranteed would be missing.** The fallback
   work was not wasted, but nobody checked why the first branch was never taken.

Fix is one line each: `Annotated[str, Form()] = ""`. It needs a multipart contract test, because
this is precisely the class of defect a unit test that calls the function directly cannot see —
the same shape as the stub-agrees-with-itself pitfall in `known-pitfalls.md`.

### C2's permission hole — a viewer can approve a section. CONFIRMED.

`services/engine/app/proposal_routes.py`: `edit_section` opens with `authz.check(user, authz.DRAFT)`.
`approve_section`, thirty lines below, has **no `authz.check` at all** — only a workspace-ownership
404 guard, whose own comment explains why it is there and does not mention permissions.

Section approval is the control that *replaces* cite-or-flag for narrative prose (B-FR4): nothing
exists to cite a forward commitment against, so a human signs it instead. That signature is the
whole guarantee, and any workspace member can currently produce it.

---

# §D — Disputed, or needing a second look before anyone acts

The audit is credible — two for two on the checks above — and that is exactly why the rest should
not be taken on trust. Four items where the finding may be describing correct behaviour:

1. **C1's "confidence 0.01 → pass".** Reproduced by calling `analysis.decide()` directly. The open
   question is whether that state is reachable through the real analyzer schema and the 0.75
   routing gate, or only by constructing the input by hand. A defect reachable only through a
   direct function call is a hardening task; one reachable through the endpoint is a Sev-1. These
   are different priorities and the report does not separate them.

2. **C3's "readiness 100% while export blocks".** Two gates disagreeing is not automatically a
   defect — they answer different questions, and `docs/test-strategy.md` is explicit that an AC is
   verified at its tagged layer only. What must be checked is the *user-visible* claim: if the
   screen says ready-to-submit while a mandatory placeholder is open, that is the bug. If the two
   numbers merely differ in an API response nobody renders side by side, it is not.

3. **C4's rubric verdict.** "Technically disqualified" from a generic rubric is the strongest
   finding in the report on principle — it is a model-shaped conclusion crossing into PRD §2.4's
   deterministic column — but the estimator and rubric already carry suppression and
   self-describing heuristic language. Confirm what the screen actually renders to a user before
   removing the feature, not what the function returns.

4. **C5's feed cap.** The 100-record limit is real, but this repo has just been through a capped-
   window bug (the 1000-row recompute, `known-pitfalls.md`) and the fix there was **filter to what
   the feature can act on**, not raise the cap. The same reasoning applies here: server-side
   open/closed filtering first, pagination second.

One thing the audit got structurally right and is worth repeating: **the 17-section IT-services
proposal template is aimed at a customer this product does not have.** The only documented design
partner manufactures wire rope and bids on catalogue lines. `docs/feedback/usha-martin.md` says
the same thing in the customer's own words, and this reviewer reached it independently from the
code alone.

---

# §N — What this file is not

It is not a plan. Nothing here is scheduled, and a P0 in §10 is the reviewer's priority, not the
product owner's. The next step is the owner picking which of §11's ten quick wins are worth an
afternoon, and which of C1-C5 need the verification in §D before they become work.
