# TenderCraft — Product Requirements Document

**Version:** 1.0 (Draft for engineering review) · **Date:** July 2026 · **Status:** Confidential — working name "TenderCraft"
**Audience:** Engineering, Data Science, Design, QA · **Owner:** Product

---

## 1. Executive Summary

TenderCraft is an AI-native SaaS platform for the Indian procurement market. It converts unstructured tender documents — GeM bid documents, CPPP/eProcure NITs, state e-procurement packages, and corporate RFPs — into a structured, verifiable criteria model, and converts a bidder's credential library into compliant, evaluator-ready proposals. It gives vendors a pre-bid eligibility lens before they spend a rupee of effort, and (in a later phase) an estimated evaluation score before they submit.

The platform has three product surfaces on one shared data model:

1. **RFP Analyzer** — upload any tender against a stored vendor profile; get per-criterion Pass/Fail/Needs-review verdicts, a quantified gap analysis, a weighted eligibility score, and a Bid/No-Bid recommendation.
2. **Proposal Generator** — criteria-mapped narrative drafts with citations to the company's content library, plus deterministically rendered design elements (cover pages, compliance matrices, organograms, financial summaries, appendix indices), inside a human-in-the-loop review workflow.
3. **Score Estimator** — a calibrated model that predicts probable technical scores, ranks weak sections by marginal score impact, and improves from win/loss feedback.

Three design doctrines govern every module:

- **AI reads and writes; deterministic logic decides.** Extraction and drafting are model tasks with confidence values and citations. Compliance verdicts, checklist coverage, numeric threshold checks, formatting validation, and export gates are deterministic functions over structured data.
- **Cite or flag.** Every generated claim traces to a source in the content library. Missing information produces an explicit "insufficient data" flag — never a plausible invention.
- **Humans approve everything that leaves the system.** No autonomous portal submission exists in any phase; the platform holds no portal write credentials.

**Headline targets:** time to first draft under 2 hours (from a 40+ hour baseline); ≥95% mandatory-criteria coverage in first drafts; eligibility prediction accuracy ≥85% with a false-positive rate below 5%; score estimates within 15% of actual technical scores with directional accuracy above 75%.

**Packaging (context, not spec):** Freemium Analyzer (3 analyses/month) → Pro (Generator + unlimited analyses) → Enterprise (Estimator, API, white-label for bid consultants). Module rollout follows this ladder deliberately: the Estimator depends on outcome telemetry that only accumulates once the Analyzer and Generator are in production.

---

## 2. Problem Statement & AI Hypothesis

### 2.1 The problem

Indian public procurement runs through GeM, CPPP/eProcure, and more than twenty state e-procurement portals; large corporate procurement mirrors the same structure. Tenders use a two-envelope system (technical bid, financial bid) governed by dense NITs containing eligibility criteria (average annual turnover, net worth, similar-work experience, ISO and other certifications, OEM authorization/MAF, EMD or bid-security declarations, MSE/DPIIT exemptions), technical evaluation matrices, compliance annexures in prescribed formats, and frequent corrigenda that silently change requirements mid-cycle.

The consequences for bidders:

- A single compliant proposal consumes **3–4 employees for at least one week**, most of it spent interpreting criteria, hunting evidence documents, and formatting annexures.
- Proposals are routinely **rejected for "document insufficiency"** — a missing mandatory undertaking, an expired certificate, an annexure in the wrong format, or an unanswered criterion — before technical merit is ever evaluated.
- Vendors have **no pre-bid visibility into eligibility**, so they forfeit tender fees, EMD handling costs, and staff weeks on bids they could never win.
- Every tender is bespoke; **static templates fail**, so each response is rebuilt largely from scratch.

### 2.2 AI hypothesis (testable form)

> If tender documents can be decomposed into structured, source-anchored criteria, mapped against a bidder's content library and structured credentials, and rendered as cited narrative plus deterministic compliance artifacts, then proposal creation time falls by ≥70%, insufficiency rejections fall by ≥50%, and non-qualifying bids are avoided via a pre-bid eligibility score with a false-positive rate below 5%.

### 2.3 Hypothesis validation plan

- Instrument baseline metrics (draft hours, rejection reasons, bids abandoned) with ~20 design partners before feature exposure.
- Measure time-to-draft on real tenders against each partner's own baseline.
- Compare insufficiency-rejection rates for the partner cohort across two quarters pre/post adoption.
- Capture win/loss and score outcomes from day one; this corpus is a prerequisite for Module D.

### 2.4 Division of labor: AI vs. deterministic logic

This table is normative. Engineers should treat any AI output crossing into the right-hand column as a defect.

| Concern | Owner |
|---|---|
| Criteria extraction and classification from tender text | AI, with confidence scores and mandatory human verification below threshold |
| Mandatory vs. desirable vs. self-attestation labeling | AI proposal → human confirmation before the tender model is locked |
| Eligibility verdicts on numeric/date/boolean criteria (turnover ≥ X, completion within Y years) | Deterministic comparators over structured profile fields |
| Fuzzy criteria matching ("similar nature of work") | AI semantic match with evidence and confidence; conservative default to human review |
| Checklist coverage, annexure inventory, formatting validation, export gates | Deterministic |
| Narrative drafting for criterion responses | AI, with mandatory citation markers |
| Financial figures inside proposals | Deterministic transclusion from library records — never model-generated |
| Score estimation | Calibrated ML model; suppressed under low data; always with rationale attribution |

---

## 3. Target Personas & Error Tolerance

### 3.1 Personas

**P1 — SME Bid Owner.** Director or founder at a 20–200 person MSME bidding on PSU and state tenders (2–5 bids/month). No dedicated bid team; the owner personally signs undertakings. Errors are existential: a forfeited EMD hurts cash flow, and a false self-declaration risks debarment. Needs certainty and plain-language rationale far more than speed.

**P2 — Enterprise Proposal Manager.** Runs a 4–10 person bid desk at a large vendor handling 15–30 concurrent responses across government and corporate RFPs. Cares about throughput, consistency of house style, evidence reuse across bids, and deadline governance. Latency is negotiable; unverifiable content in a submitted document is not.

**P3 — Bid Consultant.** Agency preparing proposals for many client companies simultaneously. Needs hard per-client workspace isolation, white-label output, and API access. A single instance of cross-client data leakage ends the relationship and the reputation.

### 3.2 Error-tolerance matrix (normative)

| ID | Error | Example | Severity | Tolerance | Primary mitigation |
|---|---|---|---|---|---|
| ET-1 | Eligibility **false positive** | "You qualify" → rejected on eligibility after paying fees | Critical | FPR < 5%; borderline never auto-passes | Deterministic gates for numeric criteria; fuzzy matches below 0.75 confidence routed to Needs-review |
| ET-2 | Eligibility **false negative** | "You don't qualify" when an exemption applied | Low | Acceptable if flagged | Every Fail shows rationale + source clause + one-click "request manual re-check" |
| ET-3 | Hallucinated claim in a proposal | Invented project experience or turnover figure | Critical | Zero uncited claims may pass the export gate | Cite-or-flag pipeline; financial values transcluded only; export blocker |
| ET-4 | Missed mandatory criterion | Undertaking annexure absent from submission | Critical | Zero at export without logged override | Deterministic coverage report against the locked tender model |
| ET-5 | Score estimate variance | Predicted 78, actual 68 | Moderate | ±15% acceptable if directional accuracy > 75% | Calibration; suppression under low data (D-AC4) |
| ET-6 | Cross-tenant data leakage | Client A's credential appears in Client B's draft | Critical | Zero tolerance | Per-tenant encryption and retrieval scoping; isolation tests in CI |

---

## 4. Module Specifications

Each module below specifies purpose, user stories, functional requirements, the AI/deterministic split, acceptance criteria (IDs are release-gate references), and the UX flow.

### Module A — Document Ingestion & Shredding Engine

**Purpose.** Convert any tender package into a locked, source-anchored **Tender Object Model (TOM)** — the single structured artifact all downstream modules consume.

**TOM contents:** tender metadata (issuing authority, tender/bid number, key dates, EMD and tender fee, pre-bid meeting details); a criteria list where each criterion carries `{id, source anchor (page + clause), verbatim text, category: eligibility | technical | financial | terms, requirement level: mandatory | desirable | self-attestation, evidence required, evaluation weight if published}`; a forms/annexure inventory; and corrigendum diffs.

**Functional requirements**

- **A-FR1** Ingest PDF, DOCX, scanned documents (OCR pipeline), and portal-exported packages (GeM bid documents, CPPP NIT + tender document + corrigenda, state portal ZIPs).
- **A-FR2** Parse document structure and extract criteria with category and requirement-level classification.
- **A-FR3** Diff corrigenda against the base tender; changed or added criteria are flagged and require re-verification.
- **A-FR4** Human verification screen: side-by-side source clause ↔ extracted criterion, with per-field confidence. Extractions below **0.80 confidence must be human-confirmed**; the TOM cannot be locked while unconfirmed low-confidence items remain.
- **A-FR5** Downstream modules (B, C, D) consume **locked TOMs only**. This is the boundary that lets compliance checks be deterministic.
- **A-FR6** OCR quality gate: scans below 98% estimated word accuracy route to manual review with structured re-upload guidance (see EC-1).

**User stories**

- **A-US1** As a Proposal Manager, I upload a 300-page tender PDF and receive a structured criteria checklist the same afternoon, so I can scope the bid immediately.
- **A-US2** As a Bid Owner, I see each extracted criterion linked to its exact page and clause, so I can trust the checklist without re-reading the tender.
- **A-US3** As a reviewer, when a corrigendum lands, I see precisely which criteria changed and re-confirm only those.

**Acceptance criteria**

| ID | Criterion | Threshold | Method |
|---|---|---|---|
| A-AC1 | Criterion extraction on gold-standard set (100 annotated tenders across GeM, CPPP, ≥3 state portals) | Recall ≥ 95%, precision ≥ 90% | Offline eval harness |
| A-AC2 | Mandatory vs. desirable vs. self-attestation classification | F1 ≥ 0.90 | Offline eval harness |
| A-AC3 | Source anchoring: every criterion in a locked TOM carries a resolvable page + clause anchor | 100% | Deterministic validator |
| A-AC4 | Processing time, tenders ≤ 300 pages | p90 ≤ 15 min upload-to-verification-queue | Production telemetry |
| A-AC5 | Lock integrity: no TOM locks with unconfirmed sub-0.80-confidence extractions | 100% | Deterministic gate + audit log |

**UX flow.** Upload → parsing progress with page-level status → verification queue (low-confidence items first) → confirm/edit/add criteria → lock TOM → handoff cards to Analyzer and Generator.

### Module B — AI Proposal Generator

**Purpose.** Turn a locked TOM plus the company's content library into a compliant, cited, formatted first draft — and make the gaps impossible to miss.

**Content library.** Past proposals, project completion certificates, purchase/work orders, audited financials and turnover certificates, ISO/CMMI and other certifications with validity dates, team CVs, org data, standard undertakings, MAF templates. Documents are chunked and indexed with metadata (document type, validity window, key values); financial and experience values are additionally stored as structured fields for transclusion.

**Generation pipeline.** For each criterion in the locked TOM: retrieve evidence (hybrid lexical + semantic search, hard-filtered by validity metadata) → draft a narrative response with inline citation markers resolving to library chunks → assemble into sections. In parallel, deterministic renderers produce the design elements: cover page from tender metadata + brand template; **compliance matrix** (criterion × response reference × evidence page reference); organogram from structured team records; financial summary tables via field transclusion; appendix index with evidence cross-references.

**Normative rules**

- **B-FR1 Cite-or-flag.** Any generated sentence without a resolvable citation is marked "unverified — provide source or attest" and cannot pass the export gate unattested.
- **B-FR2 Missing evidence → placeholder blocks** with explicit sourcing instructions (e.g., "Insert notarized copy of FY24 turnover certificate — CA-attested original required"). Placeholders block export.
- **B-FR3 Financial and numeric values are never generated.** They render only through transclusion tokens bound to library fields.
- **B-FR4 Watermarking.** AI-generated sections carry a visible watermark in all draft states; removal happens only at final export after required approvals, and the removal event is audit-logged.
- **B-FR5 Original-document flags.** Items the tender demands as notarized/attested originals are marked "original required — cannot be AI-substituted."
- **B-FR6 Outputs:** editable DOCX, print-ready PDF, and portal-assist view (structured copy blocks mapped to GeM ATC responses / CPPP form fields). Export assist only — the system never writes to portals.
- **B-FR7 Languages.** English default; Hindi via constrained translation with a human review gate before inclusion; bilingual annexure support; additional regional languages configurable in Phase 3.

**User stories**

- **B-US1** As a Proposal Manager, I generate a full first draft with a populated compliance matrix in under two hours, so my team spends its week on sharpening, not assembling.
- **B-US2** As a Bid Owner, I get a task list of every missing evidence document before I've written a word, so nothing surfaces at 11 pm on deadline day.
- **B-US3** As a Compliance Checker, I can trace any claim in the draft to its source document in one click.

**Acceptance criteria**

| ID | Criterion | Threshold | Method |
|---|---|---|---|
| B-AC1 | Time to first full draft, standard tender (≤ 50 criteria) with populated library | p90 ≤ 2 hours | Production telemetry |
| B-AC2 | Mandatory-criteria coverage in first draft (addressed or explicit placeholder) | ≥ 95% | Deterministic count from compliance matrix |
| B-AC3 | Claim verifiability: generated sentences carrying a valid citation resolving to a library chunk | ≥ 90%; remainder flagged "unverified" | Automated citation validator + 5% human sample |
| B-AC4 | Uncited financial/numeric claims at export | 0 (hard gate) | Deterministic export blocker |
| B-AC5 | Template compliance of exported documents (fonts, page limits, annexure order per portal pack) | 100% pass on template linter | Deterministic linter |

**UX flow.** Select locked TOM → map library (auto-suggested) → generate → review workspace (draft left, criterion + evidence right) → resolve flags/placeholders → approvals (Module E) → export.

### Module C — RFP Analyzer & Eligibility Engine

**Purpose.** Answer "should we bid?" before any effort is spent — per-criterion verdicts, a quantified gap list, and a Bid/No-Bid recommendation that errs conservative.

**Vendor profile schema.** Legal identity (CIN, PAN, GST, MSE/DPIIT registration status); financials (3–5 years turnover, net worth, working capital); experience records (project value, client type, scope tags, completion dates, supporting document references); certifications with expiry; key personnel qualifications; OEM/manufacturing status and authorizations.

**Evaluation logic**

- **C-FR1 Criterion router.** Each locked-TOM criterion is typed. Numeric/date/boolean criteria (e.g., "average annual turnover ≥ ₹10 Cr over FY23–FY25") evaluate through **deterministic comparators** with financial-year normalization.
- **C-FR2 Fuzzy criteria** ("three similar works of comparable nature") evaluate through AI semantic matching against experience records, returning `{verdict, cited evidence, confidence}`. Confidence below **0.75 → "Needs review"** — the model can never auto-Pass a fuzzy criterion at low confidence (protects ET-1).
- **C-FR3 Exemption overlays.** MSE/DPIIT relaxations (turnover/experience waivers, EMD exemption) apply only where the tender text grants them, applied deterministically and cited to the granting clause.
- **C-FR4 Outputs.** Per-criterion Pass / Fail / Needs-review with rationale and source clause link; gap analysis with quantified shortfalls ("average turnover ₹8.2 Cr vs. required ₹10 Cr — gap ₹1.8 Cr"; "missing: valid ISO 9001 — expired 03/2026"); weighted eligibility score; Bid/No-Bid recommendation with confidence band.
- **C-FR5 Scoring semantics.** Mandatory eligibility criteria are **gates, not weights** — one hard Fail caps the recommendation at No-Bid regardless of score. The weighted score expresses strength on desirable and scored technical criteria only.

**User stories.** **C-US1** As a Bid Owner, I upload an NIT and know within minutes whether we clear eligibility, and exactly what's missing if we don't. **C-US2** As a Consultant, I run one tender against five client profiles and see who should bid. **C-US3** As a Proposal Manager, every Fail shows me the clause it came from, so I can challenge it or fix it.

**Acceptance criteria**

| ID | Criterion | Threshold | Method |
|---|---|---|---|
| C-AC1 | Eligibility prediction accuracy vs. actual evaluator outcomes (validation cohort) | ≥ 85% | Outcome-matched eval |
| C-AC2 | False-positive rate (reported qualified, rejected on eligibility) | < 5% | Outcome-matched eval + production monitor |
| C-AC3 | Gap-detection completeness on missing mandatory items | ≥ 90% | Annotated gold set |
| C-AC4 | Verdicts carrying rationale + source clause link | 100% | Deterministic validator |
| C-AC5 | Sub-0.75-confidence fuzzy matches routed to Needs-review (never auto-Pass) | 100% | Deterministic gate + logs |

**UX flow.** Profile setup (once, guided) → upload tender / pick locked TOM → verdict dashboard (gates first) → gap list as actionable tasks → Bid/No-Bid card with confidence → one-click handoff to Generator.

### Module D — Score Estimator & Feedback Loop

**Purpose.** Before submission, estimate the probable technical score, expose weak sections, and rank improvements by marginal score impact — honestly suppressing itself when data is thin.

**Inputs.** Locked TOM (including published evaluation matrices/QCBS splits where present), the generated proposal with its compliance matrix, the vendor profile, and the historical outcome corpus (win/loss, rejection stage, disclosed technical scores, evaluator remarks where available).

**Model behavior**

- **D-FR1** Criterion-level scoring features feed a calibrated ensemble; output is a **score range**, never a point estimate presented as fact.
- **D-FR2 Cold-start suppression.** If fewer than ~30 comparable historical outcomes exist in the authority/category cluster, the estimate is suppressed and the UI shows "insufficient historical data" (threshold tunable; see Assumptions).
- **D-FR3** Weak-section list ranked by marginal score impact; each improvement suggestion carries expected delta and rationale.
- **D-FR4 Feedback loop.** Users log outcomes (won / lost / rejected + stage + scores if disclosed); quarterly recalibration; drift monitors on feature distributions and calibration error.
- **D-FR5 Privacy.** Cross-client learning uses only anonymized, consented, value-bucketed data (§6).

**User stories.** **D-US1** As a Proposal Manager, I see we're weakest on the methodology section worth 20 marks, and fix that first. **D-US2** As a Bid Owner, I deprioritize a bid with a 30% win likelihood in favor of one at 70%.

**Acceptance criteria**

| ID | Criterion | Threshold | Method |
|---|---|---|---|
| D-AC1 | Score estimate error vs. disclosed technical scores | Mean absolute error < 15% | Outcome-matched eval |
| D-AC2 | Directional accuracy (win/loss side of prediction) | > 75% | Outcome-matched eval |
| D-AC3 | Adopted suggestions associated with improved coverage/score | ≥ 60% | Suggestion telemetry + outcomes |
| D-AC4 | Suppression fires whenever cluster data is below threshold | 100% | Deterministic gate |
| D-AC5 | Estimates shipped with per-criterion rationale breakdown | 100% | Deterministic validator |

### Module E — Collaboration & Review Workflow

**Purpose.** Make the human-in-the-loop real: roles, approvals, versioning, and an audit trail strong enough for compliance review.

**Functional requirements**

- **E-FR1** Roles with RBAC: Writer, Reviewer, Compliance Checker, Legal, Approver (submission sign-off). Approval chains configurable per workspace, sequential or parallel.
- **E-FR2** Section-level assignment; comments and annotations anchored to text ranges; @mentions and notifications.
- **E-FR3** Version control with diffs and one-click restore.
- **E-FR4** **Immutable audit trail**: every content-changing action, AI generation event, verdict override, watermark removal, and export — actor, timestamp, before/after reference.
- **E-FR5** **Export lock** until all required approvals are complete; admin override exists but is prominently logged.
- **E-FR6** Deadline governance: SLA timers against tender submission deadline with escalations at T-72h/48h/24h.

**Acceptance criteria**

| ID | Criterion | Threshold | Method |
|---|---|---|---|
| E-AC1 | Content-changing actions captured in audit trail | 100% | Audit completeness test suite |
| E-AC2 | Exports without required approvals | 0 (override only via logged admin path) | Deterministic gate |
| E-AC3 | Version restore fidelity | 100% byte-identical | Automated test |
| E-AC4 | Deadline escalations fire at T-72/48/24h | 100% | Scheduler tests |
| E-AC5 | Review cycle time per stage on standard bids (ops KPI, not gate) | ≤ 24h median | Production telemetry |

---

## 5. AI Model Spec

### 5.1 Model components

| Component | Task | Inputs | Outputs | Hard constraints |
|---|---|---|---|---|
| Extractor | Tender pages → TOM candidates | Page text + layout, OCR output | Schema-valid JSON criteria with confidence + source anchors | Rejects free-text output; no criterion without an anchor; sub-0.80 items enter verification queue |
| Retriever | Evidence lookup per criterion | Criterion, library index | Ranked chunks | Validity filter (expired documents excluded) is a hard filter, not model discretion; retrieval scoped to tenant |
| Drafter | Criterion + evidence → narrative | Criterion, retrieved chunks, style config | Text with inline citation markers and transclusion tokens | Cite-or-flag; numeric values only via transclusion tokens; empty retrieval → placeholder template, never prose |
| Eligibility matcher | Fuzzy criterion vs. profile | Criterion, experience records | `{verdict, evidence, confidence}` | < 0.75 → Needs-review; cannot emit Pass on empty evidence |
| Score model | Proposal + TOM + history → estimate | Engineered criterion-level features | Score range + per-criterion attribution | Suppression rule (D-FR2); attribution mandatory |
| Translator | Approved EN section → HI/regional | Approved English text | Translated section | Human review gate before inclusion in any export |

### 5.2 Global guardrails (normative)

- **G-1 No autonomous submission.** The platform holds no portal write credentials in any phase. Output is export-assist; the user remains bidder of record.
- **G-2 No generated financial commitments.** Revenue projections, pricing, turnover figures, and guarantees appear only when explicitly provided by the user, via transclusion.
- **G-3 Watermarking.** AI-generated sections are watermarked until approved final export; removal is logged (B-FR4).
- **G-4 Explainability.** Every verdict and estimate ships with a rationale. "The model said so" is a defect, not an answer.
- **G-5 Insufficient data → explicit flag.** A hallucinated fact that passes gates is a Sev-1 defect with mandatory RCA.
- **G-6 Untrusted-input defense.** Tender documents are third-party content. Instruction-like text inside them is treated as data: the extractor runs with an allowlisted output schema, and no tool call, fetch, or side effect can be triggered by document content.
- **G-7 Authenticity.** The system flags original-required documents and refuses attempts to fabricate certificates, experience records, or attestations; refusals are logged tamper-evidently.

### 5.3 Model operations

Gold sets per module with versioned annotations; release gates tied to the AC tables in §4; no model or prompt change ships if any gate metric regresses more than 2 points on gold sets; canary tender set re-run on every change; 5% human evaluation sampling of production drafts; versioned prompts and models with one-step rollback (§8).

---

## 6. Data & Content Requirements

- **Annotation corpus.** ≥ 500 tenders annotated for criteria spans, categories, and requirement levels, spanning GeM, CPPP, at least five state portals, and corporate RFPs; refreshed quarterly because portal formats drift.
- **Outcome corpus.** Win/loss, rejection stage, and technical scores where disclosed — sourced from user-logged outcomes and public award disclosures (CPPP award notices, GeM contract listings). This corpus gates Module D's launch.
- **Content library ingestion.** Direct upload plus Drive/SharePoint connectors; auto-classification of document type with human confirmation; validity tracking with expiry alerts; structured field capture for financials, projects, and personnel.
- **Isolation and consent.** Per-tenant encryption; retrieval indices scoped per tenant (per client workspace for consultants). **No training on customer content by default**; cross-client learning only with explicit opt-in, identity stripped and values bucketed. Deletion within 30 days of request; backups purged within 90.
- **Provenance.** Every library chunk retains source document, page, and upload actor — required for citation resolution (B-AC3).

---

## 7. Success Metrics & Evaluation Framework

**North star:** compliant submissions produced per active customer per month.

**Business and adoption metrics**

| Metric | Target |
|---|---|
| Activation: first analysis within 24h of signup | ≥ 60% |
| Draft-time reduction vs. customer's own baseline | ≥ 70% |
| Insufficiency-rejection reduction, design-partner cohort, two quarters | ≥ 50% |
| Analyzer → Pro conversion | ≥ 8% (assumption — revisit with pricing) |

**Quality gates** are the module AC tables (§4): A-AC1–5, B-AC1–5, C-AC1–5, D-AC1–5, E-AC1–4. Release rule: any gate metric regressing > 2 points on gold sets blocks the release.

**Production monitors:** rolling eligibility FPR reconciled against user-reported outcomes; citation validity rate; verdict override rate (a rising override rate signals model or UX drift); score-suppression rate; per-portal extraction accuracy. Quarterly calibration review for Module D; fairness audit per §9.

---

## 8. Edge Cases, Fallbacks & Rollback Criteria

### 8.1 Edge cases and fallbacks

| ID | Case | Behavior |
|---|---|---|
| EC-1 | Illegible or incomplete tender documents | Route to manual review with structured re-upload guidance (which pages, expected sections); never guess |
| EC-2 | Conflicting criteria within a tender, or corrigendum contradicting the base | Flag ambiguity, present each compliant interpretation side-by-side, require explicit user selection, log the choice |
| EC-3 | Insufficient content library for a criterion | Placeholder with sourcing instructions; placeholders block export (B-FR2) |
| EC-4 | Unknown portal format | Fall back to generic template pack with a visible warning; template library covers GeM, CPPP, and major state portals at launch |
| EC-5 | Low-confidence score estimate | Suppress and show "insufficient historical data" (D-FR2) |
| EC-6 | Model/API outage | Queue jobs, notify users, preserve drafts; deterministic features (locked-TOM checklist, compliance matrix, gap list) remain fully available |
| EC-7 | Oversized tenders (> 1,000 pages) | Chunked processing with extended-SLA notice; verification queue paginates by section |

### 8.2 Rollback criteria (automatic unless noted)

| ID | Trigger | Action |
|---|---|---|
| RB-1 | Production eligibility FPR > 5% over a rolling 4 weeks | Disable Bid/No-Bid recommendation (gap-analysis-only mode), notify users, RCA before re-enable |
| RB-2 | Citation validity < 95% in any weekly window | Pin Drafter to last known-good model/prompt version |
| RB-3 | Extraction canary recall drops > 3 points after any change | Auto-rollback the extraction version |
| RB-4 | Score directional accuracy < 70% for an authority/category cluster | Suppress estimates for that cluster until recalibrated |

---

## 9. Security, Compliance & Responsible AI

**Legal baseline (India).** DPDP Act 2023 and its Rules: consent notices, purpose limitation, data-principal rights (access, correction, erasure), and breach notification obligations. IT Act 2000 including reasonable-security-practices obligations. CERT-In 2022 directions: incident reporting within prescribed timelines and mandated log retention. Company financials, credentials, and bid content are treated as confidential business information regardless of personal-data status. (Engineering note: verify current DPDP Rules requirements at build time; the regime is young and evolving.)

**Data residency.** All customer data at rest in Indian regions. Enterprise tier offers hosting on MeitY-empanelled cloud for government-adjacent clients.

**Security controls.** Encryption in transit and at rest; per-tenant keys; RBAC everywhere with SSO on Enterprise; immutable audit storage; periodic VAPT; ISO 27001 and SOC 2 on the certification roadmap. **DSC handling:** the platform never stores users' digital-signature private keys; signing is performed by the user client-side, and the platform only marks signature placement.

**Portal integrity.** Read/assist only; no credentialed scraping in violation of portal terms; no automated bid submission (G-1); the user remains bidder of record. Product copy must state that outputs are decision support, not legal advice. No feature may fabricate credentials — attempts are refused and logged (G-7).

**Responsible AI.** Human-in-the-loop gates at TOM lock, draft approval, and export; watermarking and full claim traceability; explainable verdicts and estimates; a subgroup fairness audit at every Module D recalibration (the estimator must not systematically penalize MSEs or new entrants relative to outcome-matched incumbents); internal model cards per component.

---

## 10. Roadmap & Phases

| Phase | Scope | Exit gates |
|---|---|---|
| **PH0 — Foundations** (~8 weeks) | Annotation corpus, TOM schema, eval harness, design-partner recruitment | Gold sets live; extraction baseline measured |
| **PH1 — MVP** (~4 months) | Module A + Module C, minimal content library, verification UX; Freemium Analyzer | A-AC1–5 and C-AC1–5 pass on gold sets; 20 design partners; ≥ 100 real analyses |
| **PH2 — Growth** (~6 months) | Module B + Module E, DOCX/PDF export, GeM/CPPP template packs, Hindi, Pro tier | B-AC1–5 and E-AC1–4 pass; time-reduction study ≥ 70% across ≥ 30 real bids |
| **PH3 — Scale** | Module D (once outcome corpus crosses threshold), Enterprise API + white-label, regional languages, SSO/advanced audit, expanded state-portal packs | D-AC1–5 pass; VAPT clean; enterprise readiness review |

**Sequencing rationale.** Analyzer-first builds user trust on low-risk output and accumulates the outcome telemetry the Estimator requires; the Generator without a locked TOM discipline would be a hallucination machine. Module D last is a data dependency, not a preference.

---

## 11. Appendices

### Appendix A — Competitive landscape (categories)

| Category | Examples | Gap TenderCraft exploits |
|---|---|---|
| Tender discovery/aggregators | TenderTiger, Tender247, BidAssist | Find tenders; don't author, verify eligibility, or generate compliant documents |
| Global RFP-response suites | Responsive (RFPIO), Loopio, QorusDocs, AutogenAI | Built for Western RFP conventions; no GeM/CPPP structure awareness, annexure formats, or MSE-exemption logic; pricing misfit for Indian SMEs |
| Generic AI writing tools | Horizontal LLM assistants | No determinism, traceability, compliance gates, or audit trail — unusable where a false claim risks debarment |
| Manual bid consultants | Incumbent workflow | Slow and expensive — but also a distribution channel via Enterprise white-label |

Wedge: India-format-native shredding + deterministic compliance + a pre-bid eligibility lens. (Feature sets shift; re-verify during GTM research.)

### Appendix B — Glossary

| Term | Meaning |
|---|---|
| NIT | Notice Inviting Tender |
| GeM | Government e-Marketplace, the central government procurement portal |
| CPPP / eProcure | Central Public Procurement Portal and its e-tendering system |
| EMD | Earnest Money Deposit (bid security) |
| PBG | Performance Bank Guarantee |
| MAF | Manufacturer's Authorization Form |
| QCBS | Quality and Cost Based Selection (weighted technical + financial evaluation) |
| L1 / T1 | Lowest financial bidder / top technical scorer |
| ATC | Additional Terms & Conditions (GeM) |
| MSE / DPIIT | Micro & Small Enterprise / Startup recognition — trigger exemptions in many tenders |
| DSC | Digital Signature Certificate used for portal signing |
| Corrigendum | Official amendment to a published tender |
| Two-bid system | Separate technical and financial envelopes, opened sequentially |
| TOM | Tender Object Model — TenderCraft's locked, structured representation of a tender |
| Insufficiency rejection | Rejection for missing/incorrect documents before merit evaluation |

### Appendix C — Assumptions register (veto these)

| # | Assumption | Confidence |
|---|---|---|
| 1 | Portal write-integration (auto-submission) is excluded from scope in all phases, not just v1 | High |
| 2 | Customer content is never used for cross-client training absent explicit opt-in | High |
| 3 | 0.75 confidence threshold for fuzzy-criterion review routing | Medium — tune against FPR data in PH1 |
| 4 | ~30 comparable outcomes as the Module D suppression threshold | Medium — tune per cluster |
| 5 | Hindi in PH2, other regional languages PH3; freemium at 3 analyses/month | Low — pricing and language priority need market input |

*— End of document —*
