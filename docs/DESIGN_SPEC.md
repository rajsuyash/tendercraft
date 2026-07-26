# Design Spec — TenderCraft

## §A Spec header

| Field | Value |
|---|---|
| Status | approved (2026-07-23T16:27:07Z) |
| PRD | tendercraft-PRD.md · sha256: 915d25d1 |
| Designer | stitch-ux-designer v1.0.0 · mode: mcp |
| Stitch | project: 4504009752110417749 · server: official · renders: true |
| Platform | web (desktop-first, 1280px+ primary) · Locales: en (hi token stacks reserved, PH2) |

> Note: the PRD contains no explicit routes section; **all routes below are DERIVED** from module UX flows (§4 of the PRD) and are the canonical route contract for scaffold and planning.

## §B Design language

**Adjectives:** trustworthy, precise, calm, audit-ready · **Audience:** SME bid owners (P1), enterprise proposal managers (P2), bid consultants (P3) · **Density:** dense · **Theme:** light · **References:** Linear, Vanta
**Anchor screen:** S7 (verdict dashboard exercises every shared component — verdict chips, confidence badges, source anchors, gap cards, dense tables — on real analysis data)

## §C Tokens (extracted Design DNA — canonical file: `design/tokens.json`)

> **Revision `ios-2026-07-26`.** The system was restyled to an Apple HIG-flavoured language on
> request. Token **names**, the layout grid, and the reserved verdict semantics are unchanged —
> only values moved — so every screen spec in §E and every design AC in §H still applies as
> written. What changed is how it looks, not what it must prove.

| Token | Value | Notes |
|---|---|---|
| color.primary | #0066CC | iOS system blue, darkened until white-on-it passes 4.5:1 (5.57:1) |
| color.surface / color.surface-alt | #FFFFFF / #F2F2F7 | iOS systemGroupedBackground; cards sit on the tint, 1px #D6D6DB hairline |
| color.success / danger / warning | #207B37 / #D70015 / #8A6100 | **verdict semantics: Pass / Fail / Needs-review — reserved, never repurposed.** iOS system green/red/orange darkened until each clears 4.5:1 on its own tint; the raw system colours do not |
| color.info | #4B4ACF | iOS indigo, darkened |
| font.heading / font.body | San Francisco via `-apple-system` | one family at every size, per Apple. Inter is the cross-platform fallback (`--font-body-fallback`); 'Noto Sans Devanagari' retained in both stacks (PH2 Hindi). Lexend dropped |
| type.scale | 12/13/15/17/20/22/28/34 | body **15px** (was 14). Mirrors the iOS text styles; negative tracking from 20px up |
| space.base | 4px | page padding 24px · card padding 16px · table rows 44px · sidebar fixed 280px — **unchanged** |
| radius | 10px controls / 16px cards / 20px sheets | chips full-round |
| elevation | two-layer | tight contact shadow + wide soft shadow; a single blurred shadow reads as Material, not Apple |
| motion | cubic-bezier(0.32, 0.72, 0, 1) | ~critically-damped iOS spring · 150/220/320ms · always degrades under `prefers-reduced-motion` |
| material | rgba(255,255,255,0.72) + blur(20px) saturate(180%) | **chrome only** — sidebar, toolbars, sheets. Data surfaces stay opaque: frosting a dense compliance table costs contrast and paint time for no gain |
| breakpoints | sm 640 / md 768 / lg 1024 / xl 1280 | desktop-first; below lg the sidebar collapses |

**GLB-D1 re-verified after the restyle:** all 19 foreground/background pairs clear 4.5:1
(narrowest: `text-muted` on `surface-alt` at 4.54, `success` on `success-bg` at 4.87). The check
is scripted — see the contrast harness in the restyle commit.

## §D Screen inventory

| ID | Route | Modules | ACs rendered | States designed | Reference | Source |
|----|-------|---------|--------------|-----------------|-----------|--------|
| S1 | /login (derived: auth) | — | — | ☑def ☑err ☐load ☐empty | design/reference/S1-login.png, .html | stitch |
| S2 | /dashboard (derived: home) | E | E-FR6 | ☑def ☐load ☐empty ☐err | design/reference/S2-dashboard.png, .html | stitch |
| S3 | /tenders/upload | A | A-FR1, A-AC4 | ☑def ☑load ☑err ☐empty | design/reference/S3-upload.png, .html | stitch |
| S4 | /tenders/:id/verify | A | A-FR4, A-AC5 | ☑def ☑err ☐load ☐empty | design/reference/S4-verify.png, .html | stitch |
| S5 | /tenders/:id | A | A-FR3 | ☑def ☐load ☐empty ☐err | design/reference/S5-tender-detail.png, .html | stitch |
| S6 | /profile | C | profile schema | ☑def ☑err(missing fields) ☐load ☐empty | design/reference/S6-profile.png, .html | stitch |
| S7 | /tenders/:id/analysis | C | C-FR4, C-FR5, C-AC4 | ☑def ☐load ☐empty ☐err | design/reference/S7-analysis.png | stitch (anchor) |
| S8 | /library | B | library, §6 provenance | ☑def ☑err(expiry) ☐load ☐empty | design/reference/S8-library.png, .html | stitch |
| S9 | /proposals/:id | B | B-FR1–B-FR5 | ☑def ☑err(flags/placeholders) ☐load ☐empty | design/reference/S9-proposal-workspace.png, .html | stitch |
| S10 | /proposals/:id/export | B, E | B-AC4, B-AC5, E-AC2 | ☑def ☑err(blockers) ☐load ☐empty | design/reference/S10-export-gate.png, .html | stitch |
| S11 | /proposals/:id/score | D | D-FR1–D-FR3 | ☑def ☑err(suppression) ☐load ☐empty | design/reference/S11-score.png, .html | stitch |
| S12 | /settings | E | E-FR1–E-FR4 | ☑def ☐load ☐empty ☐err | design/reference/S12-settings.png, .html | stitch |
| S13 | /error (derived: error boundary + 404) | — | EC-6 | ☑def(=err) | design/reference/S13-error.png, .html | stitch |

Unchecked states are **specified-only** in §E (quota etiquette: default+inline-error rendered; loading/empty written).

**Shared components:**
- **C1** Sidebar nav, fixed 280px (all screens except S1, S13-404 strip)
- **C2** Dense data table — 44px rows, sticky header (S4, S5, S6, S7, S8, S10, S12)
- **C3** Criterion card — verbatim quoted clause + page/clause anchor link + verdict chip (S4, S7, S9)
- **C4** Verdict/confidence chip — Pass/Fail/Needs-review hues + numeric confidence badge (S4, S5, S7, S8, S9, S10)
- **C5** Citation chip — doc name + page pill, click reveals source (S6, S8, S9, S10)
- **C6** SLA deadline chip — neutral > amber (T-48h) > red (T-24h) escalation (S2, S5, S7)

## §E Per-screen specs

### S1 — Sign in · `/login`
**Purpose:** Authenticate into a workspace. · **Primary action:** Sign in.
**Layout:** Split — left 45% brand panel (#1F4E79, wordmark, tagline, 3 trust bullets), right 55% form card.
**Components:** form card, SSO secondary button (Enterprise).
**Data shown:** email, password; freemium hook "Start free — 3 analyses/month"; footer "Outputs are decision support, not legal advice."
**States:**
| State | Trigger | Design |
|---|---|---|
| default | — | per reference render |
| loading | sign-in request | button spinner + disabled form |
| error | bad credentials | rendered: red field border + "Incorrect email or password. N attempts remaining." |
**Interactions:** Enter submits; SSO routes to IdP.
**Design ACs:**
- **S1-D1:** Auth error renders `[data-auth-error]` inline under the password field — never a toast-only error. *Check: DOM with failed login.*
- **S1-D2:** Brand panel hides below md; form remains centered single-column. *Check: screenshot @ 768.*

### S2 — Dashboard · `/dashboard`
**Purpose:** One glance = what needs attention across concurrent bids. · **Primary action:** Upload Tender.
**Layout:** C1 sidebar / KPI card row (4) / Deadlines list (main, sorted by submission deadline) / right rail "Needs your attention".
**Components:** C1, C6 SLA chips, stage-pill progress (TOM locked → Analysis → Draft % → Approvals n/m).
**Data shown:** active tenders count, verification backlog with low-confidence count, per-tender cards: tender no. + title, portal tag (GeM/CPPP/state), value chip, SLA chip, next required action.
**States:**
| State | Trigger | Design |
|---|---|---|
| default | — | per reference render |
| loading | dashboard fetch | skeleton cards (KPI row + 3 deadline cards), never spinner-only |
| empty | new workspace | illustration + "Upload your first tender" primary CTA + 3-step explainer |
| error | fetch failure | inline banner + retry; cached list shown grey if available |
**Interactions:** deadline card click → S5; attention card CTAs deep-link (verify queue, corrigendum diff, library).
**Design ACs:**
- **S2-D1:** SLA chips use warning tokens at T-48h and danger tokens at T-24h (computed styles resolve to `--color-warning`/`--color-danger`). *Check: DOM + computed style with seeded deadlines.*
- **S2-D2:** Empty workspace renders `[data-empty-state]` with CTA to /tenders/upload — a bare deadlines region never renders. *Check: DOM with fixtures cleared.*

### S3 — Upload Tender · `/tenders/upload`
**Purpose:** Ingest any tender package; make pipeline progress and quality gates visible. · **Primary action:** Drop/browse files.
**Layout:** Left: dropzone card + processing list. Right: "What happens next" explainer + recent uploads table (C2).
**Components:** dropzone, per-file progress with stage steps (Uploaded → OCR → Structure parse → Criteria extraction → Verification queue), C2.
**Data shown:** file name, portal, page count, page-level parse progress ("Parsing page 214/300"), ETA chip "p90 ≤ 15 min" (A-AC4).
**States:**
| State | Trigger | Design |
|---|---|---|
| default | — | per reference render (includes in-progress row) |
| loading | per-file processing | inline stage steps + progress bar (rendered) |
| empty | no uploads yet | dropzone remains hero; recent-uploads table hidden, not empty-bordered |
| error | EC-1 OCR < 98% | rendered: amber row + "routed to manual review" + re-upload guidance link naming illegible pages |
| error | EC-7 > 1,000 pages | rendered: info chip "chunked processing, extended SLA" |
**Interactions:** drag-over highlight; row click → S4 when verification-ready.
**Design ACs:**
- **S3-D1:** OCR-gate failure renders `[data-ocr-gate-warning]` with a re-upload guidance affordance; never a silent failure row. *Check: DOM with EC-1 fixture.*
- **S3-D2:** Stage steps render all 5 pipeline stages in order for any in-progress file. *Check: DOM.*

### S4 — Verification Queue · `/tenders/:id/verify`
**Purpose:** Human confirmation of low-confidence extractions; the gate that makes the TOM lockable (A-FR4/A-AC5). · **Primary action:** Confirm criterion.
**Layout:** Three panes — queue rail 300px (low-confidence first) / source clause panel (rendered page excerpt, highlighted sentence, anchor chip) / extracted-criterion form card.
**Components:** C3, C4 confidence badges, segmented requirement-level control, ambiguity banner (EC-2) with side-by-side interpretation cards.
**Data shown:** verbatim clause text, page + clause anchor ("p.12 · Cl. 4.1(a)"), per-field confidence, evidence-required text, progress "38 of 47 confirmed · 3 low-confidence remaining".
**States:**
| State | Trigger | Design |
|---|---|---|
| default | — | per reference render |
| loading | criterion fetch | skeleton on center+right panes; queue rail stays interactive |
| empty | all confirmed | center shows "All criteria confirmed" + enabled Lock TOM |
| error | EC-2 conflict/corrigendum contradiction | rendered: amber banner, two interpretation cards, explicit selection required, logged |
**Interactions:** queue keyboard navigation (↑/↓ + Enter confirms); confirm advances to next unconfirmed.
**Design ACs:**
- **S4-D1:** Lock TOM button carries `disabled` + `[data-lock-blocked-count]` whenever unconfirmed sub-0.80 items exist (A-AC5's UI face). *Check: DOM with low-confidence fixture.*
- **S4-D2:** Every queue item renders a numeric confidence badge; sub-0.80 badges resolve to warning/danger tokens. *Check: DOM + computed style.*
- **S4-D3:** Ambiguity state renders `[data-ambiguity-banner]` with ≥2 selectable interpretation cards. *Check: DOM with EC-2 fixture.*

### S5 — Tender Detail (Locked TOM) · `/tenders/:id`
**Purpose:** The locked TOM as browsable ground truth + corrigendum diffs + handoffs. · **Primary action:** Generate Proposal / Run Analysis.
**Layout:** Header (title, TOM LOCKED chip with actor+date, authority) / metadata strip cards (deadline, EMD with exemption note, fee, pre-bid, two-bid chip) / tabs: Criteria · Forms & Annexures · Corrigenda (n) · Handoffs / C2 grouped criteria table / right rail: annexure inventory + handoff cards.
**Components:** C1, C2, C4, C6, corrigendum diff rows (amber highlight, old→new with strikethrough).
**Data shown:** criteria grouped by category with requirement-level pills, evidence required, source anchors, published weights.
**States:**
| State | Trigger | Design |
|---|---|---|
| default | — | per reference render |
| loading | TOM fetch | skeleton table + metadata strip |
| empty | (unlocked TOM routed here) | redirect to S4 with notice — no unlocked browsing |
| error | A-FR3 corrigendum changes | rendered: amber diff rows + "re-verified ✓" tags |
**Interactions:** anchor links open source page reference; handoff cards → S7/S9.
**Design ACs:**
- **S5-D1:** Every criterion row renders a source-anchor link matching `p.\d+ · Cl\.` (A-AC3's UI face). *Check: DOM.*
- **S5-D2:** Corrigendum-changed rows render `[data-corrigendum-diff]` with old value struck through. *Check: DOM with corrigendum fixture.*

### S6 — Vendor Profile · `/profile`
**Purpose:** The structured profile eligibility runs against; make gaps that block analysis visible. · **Primary action:** Update profile.
**Layout:** Header with completeness meter / left column: legal identity, financials (C2 with computed 3-yr average card), experience records (C2) / right column: certifications with validity, key personnel, OEM & authorizations.
**Components:** C2, C5 document-reference chips, validity chips (danger for expired), completeness meter.
**Data shown:** CIN/PAN/GST/Udyam, FY-wise turnover with CA-cert chips, computed averages, experience rows with evidence docs, cert expiry, MAF status.
**States:**
| State | Trigger | Design |
|---|---|---|
| default | — | per reference render |
| loading | profile fetch | section skeletons |
| empty | first run | guided setup: sections as a checklist with per-section CTAs (C UX flow "guided") |
| error | missing/expired blocking items | rendered inline: empty required field helpers + expired-cert danger chips with impact copy ("blocks 2 active bids") |
**Interactions:** inline edit per field; document chips open source.
**Design ACs:**
- **S6-D1:** Expired certifications render danger-token chips with `[data-expired-cert]`; valid ones success-token. *Check: DOM + computed style with expiry fixture.*
- **S6-D2:** Completeness meter reflects blocking items and names the count ("N items block accurate analysis"). *Check: DOM.*

### S7 — Eligibility Analysis · `/tenders/:id/analysis` (ANCHOR)
**Purpose:** "Should we bid?" — verdicts, quantified gaps, conservative recommendation (C-FR4/5). · **Primary action:** Generate Proposal (or fix gaps).
**Layout:** Header (tender, deadline chip, actions) / 3 summary cards: Bid/No-Bid verdict + confidence band · weighted score with gates-not-weights caption · criteria summary counts / "Mandatory gates first" C2 table (Criterion · Requirement · Your position · Verdict · Source) / right rail 360px gap-analysis task cards.
**Components:** C1, C2, C3, C4, C6, gap cards with "Request manual re-check" ghost link (ET-2).
**Data shown:** quantified gaps ("₹8.2 Cr — gap ₹1.8 Cr"), exemption overlays cited to granting clause (C-FR3), confidence badges on fuzzy matches, "Why?" rationale affordance per verdict (C-AC4, G-4).
**States:**
| State | Trigger | Design |
|---|---|---|
| default | — | per reference render |
| loading | analysis run | summary-card + table skeletons with "Re-running analysis" note |
| empty | no analysis yet | CTA card "Run eligibility analysis" with profile-completeness precheck |
| error | analysis failure / EC-6 | banner + retry; last completed analysis stays visible with timestamp |
**Interactions:** verdict row expand → rationale + source clause; gap card → deep link (profile/library); "Request manual re-check" on every Fail.
**Design ACs:**
- **S7-D1:** A hard mandatory Fail forces the recommendation card to No-Bid styling (danger tokens) regardless of weighted score shown (C-FR5). *Check: DOM + computed style with fail fixture.*
- **S7-D2:** Every verdict row renders both a rationale affordance and a source-clause link (C-AC4). *Check: DOM.*
- **S7-D3:** Needs-review chips render warning tokens and a confidence badge < 0.75 never co-occurs with a Pass chip in the same row (C-AC5's UI face). *Check: DOM with fuzzy-match fixture.*

### S8 — Content Library · `/library`
**Purpose:** Evidence corpus with validity tracking and provenance (B library, §6). · **Primary action:** Upload documents.
**Layout:** Header (search, type/validity filter chips, upload + connector buttons) / expiry alert banner / C2 documents table / right rail: structured-fields panel for selection with provenance footer.
**Components:** C2, C4 classification-confidence badges, C5, validity chips, confirm-classification row state.
**Data shown:** doc name, auto-classified type + confidence, structured key values ("FY25 turnover: ₹9.7 Cr"), validity, usage count, provenance (uploader, date, page anchor).
**States:**
| State | Trigger | Design |
|---|---|---|
| default | — | per reference render |
| loading | list fetch | table skeleton |
| empty | no documents | illustration + upload CTA + connector CTA (Drive/SharePoint) |
| error | expired documents | rendered: amber banner "expired documents are hard-excluded from retrieval" + danger chips per row |
**Interactions:** row select → structured-fields panel; low-confidence classification rows expose Confirm/Reclassify.
**Design ACs:**
- **S8-D1:** Expired rows render `[data-validity="expired"]` with danger-token chip; the banner names the hard-exclusion consequence. *Check: DOM with expiry fixture.*
- **S8-D2:** Structured-fields panel renders a provenance footer (uploader · date · page) for any selected document (§6 provenance / B-AC3 dependency). *Check: DOM.*

### S9 — Proposal Review Workspace · `/proposals/:id`
**Purpose:** Human-in-the-loop editing where cite-or-flag is impossible to miss (B-FR1–5). · **Primary action:** Resolve flags → Send to approvals.
**Layout:** Top bar (coverage meter, stage pills, actions) / split: editor 60% / right panel 40% with tabs Criterion · Evidence · Comments.
**Components:** C3, C4, C5, AI DRAFT watermark tag (B-FR4), transclusion token style (dotted underline + lock glyph, B-FR3), unverified-sentence flag block (B-FR1), placeholder block (dashed card, B-FR2/EC-3).
**Data shown:** draft narrative with inline citation chips, retrieved evidence chunks with relevance, criterion card with verbatim clause, coverage "46 of 47 · 1 placeholder open".
**States:**
| State | Trigger | Design |
|---|---|---|
| default | — | per reference render |
| loading | generation in progress | per-section skeleton + "Drafting §n" stage note |
| empty | criterion with no evidence | placeholder block with sourcing instructions — never generated prose (Drafter constraint) |
| error | unverified sentence | rendered: amber flag "UNVERIFIED — provide source or attest" with Attach/Attest/Delete |
**Interactions:** citation chip click reveals source chunk (B-US3, one click); transcluded values not editable inline; comment threads anchored to ranges (E-FR2).
**Design ACs:**
- **S9-D1:** Unapproved sections render `[data-ai-watermark]`; the tag is absent only post-approval (B-FR4). *Check: DOM in draft vs approved fixture.*
- **S9-D2:** Numeric/financial values in the draft render as transclusion tokens (`[data-transclusion]`) and are not contentEditable (B-FR3). *Check: DOM.*
- **S9-D3:** Placeholder blocks render `[data-placeholder-block]` with sourcing instructions and are counted in the top-bar coverage meter (B-FR2). *Check: DOM with missing-evidence fixture.*

### S10 — Export & Compliance Gate · `/proposals/:id/export`
**Purpose:** The deterministic gate: coverage, blockers, approvals — export impossible until clean (B-AC4, E-AC2). · **Primary action:** Export final documents (disabled until gate clears).
**Layout:** Header (export button + blocker helper + logged-override ghost) / compliance matrix C2 65% / right rail 35%: approval chain card, export formats card, watermark note, audit-trail preview.
**Components:** C2, C4, C5, approval chain steps (sequential status), disabled export format cards with lock icons.
**Data shown:** criterion × requirement level × response section ref × evidence (doc+page) × status; coverage footer "45/47 (95.7%) — export requires 47/47 or logged override"; original-required info chips (B-FR5).
**States:**
| State | Trigger | Design |
|---|---|---|
| default (blocked) | open blockers | per reference render — disabled primary + red helper naming blocker count |
| default (clear) | all covered + approved | enabled export; formats unlocked |
| loading | matrix computation | matrix skeleton |
| error | override used | prominent logged-override confirmation naming the audit consequence (E-FR5) |
**Interactions:** blocker row click → deep link to S9 location; "Remind" on pending approver.
**Design ACs:**
- **S10-D1:** With any open blocker, the export button is `disabled` and `[data-blocker-count]` > 0; blocker rows render danger tokens (B-AC4/E-AC2 UI face). *Check: DOM with blocker fixture.*
- **S10-D2:** Original-required items render `[data-original-required]` info chips — never a Covered/green state from an AI substitute (B-FR5). *Check: DOM.*
- **S10-D3:** Admin override is a secondary-styled control with warning iconography and never the visual primary. *Check: DOM + computed style.*

### S11 — Score Estimate · `/proposals/:id/score`
**Purpose:** Honest pre-submission score prediction: range, weak sections, suppression (D-FR1–3). · **Primary action:** Open weakest section.
**Layout:** Header (cluster/calibration chip) / hero range-band card with threshold marker / weak-sections ranked list with expected-delta chips / right rail per-criterion rationale C2 + disclosure footer.
**Components:** range-band visualization, delta chips, rationale table, suppressed-state card (muted).
**Data shown:** score range (62–74/100), threshold marker, likelihood copy, per-suggestion expected delta + rationale (D-FR3), per-criterion attribution (D-AC5).
**States:**
| State | Trigger | Design |
|---|---|---|
| default | — | per reference render |
| loading | estimation run | hero + list skeletons |
| empty/suppressed | D-FR2 cluster below threshold | rendered: muted card "insufficient historical data — estimate suppressed" — never a fabricated number |
| error | model outage EC-6 | banner; deterministic content (coverage, gap list links) remains |
**Interactions:** suggestion "Open section" → S9 anchor; "How is this computed?" reveals methodology.
**Design ACs:**
- **S11-D1:** The estimate always renders as a range visualization — no single-point number anywhere in the hero (D-FR1). *Check: DOM.*
- **S11-D2:** Suppressed state renders `[data-estimate-suppressed]` and no numeric estimate is present in the DOM (D-AC4's UI face). *Check: DOM with low-data fixture.*
- **S11-D3:** Every rendered suggestion carries an expected-delta chip and rationale text (D-AC5). *Check: DOM.*

### S12 — Workspace Settings · `/settings`
**Purpose:** RBAC, approval chains, immutable audit, deadline governance (E-FR1–4, E-FR6). · **Primary action:** Invite member.
**Layout:** Tabs: Members & Roles · Approval chains · Audit log · Deadlines & alerts / members C2 / chain-builder preview (sequential|parallel segmented) / right rail: audit-log preview (mono timestamps, filter chips) + escalation config card.
**Components:** C2, role chips, chain node cards, audit rows, T-72/48/24 escalation rows with recipient chips.
**Data shown:** member roles incl. Compliance Checker/Legal/Approver, chain order, audit entries (verdict override with reason, watermark removal, exports), escalation channels per threshold.
**States:**
| State | Trigger | Design |
|---|---|---|
| default | — | per reference render |
| loading | tab fetch | table skeleton |
| empty | single-member workspace | invite CTA card + role explainer |
| error | SSO unconfigured (Enterprise) | neutral chip, not an error banner |
**Interactions:** chain builder drag-order; audit rows expand to before/after reference (E-FR4).
**Design ACs:**
- **S12-D1:** Audit-log preview renders override and watermark-removal event types with actor + timestamp (E-FR4's UI face). *Check: DOM with seeded audit fixture.*
- **S12-D2:** Escalation config renders all three thresholds (T-72h/48h/24h) with at least one recipient each (E-AC4 dependency). *Check: DOM.*

### S13 — Service Degraded / Error Boundary · `/error` (+404)
**Purpose:** EC-6 honesty: model outage never looks like data loss; deterministic features stay discoverable.
**Layout:** Centered stack — primary outage card (queued jobs count, notify promise) / "Still available right now" 3-item grid with success chips / minimal 404 strip.
**States:** default is the error state; 404 variant strip.
**Design ACs:**
- **S13-D1:** Outage card renders `[data-queued-jobs]` count and the available-features grid lists ≥3 deterministic features with success-token chips (EC-6). *Check: DOM.*

## §F Accessibility & responsive baseline (applies to every screen)

Contrast ≥ 4.5:1 body / 3:1 large text against §C surfaces · visible focus ring on every interactive element · all states reachable by keyboard · verdict chips never rely on color alone (each carries text: PASS/FAIL/NEEDS REVIEW) · breakpoints per §C: below lg the C1 sidebar collapses behind a toggle; C2 tables horizontally scroll inside their container, the page never scrolls horizontally. Global design ACs:
- **GLB-D1:** Token contrast pairs (text/surface, verdict fg/bg) pass 4.5:1. *Check: contrast calc on tokens + spot screenshots.*
- **GLB-D2:** At 1024px, C1 collapses behind `[data-nav-toggle]` and content reflows single-region. *Check: screenshot + DOM @ 1024.*
- **GLB-D3:** Verdict chips include their label text, not color-only. *Check: DOM sample.*

## §G Out of scope (design non-goals)

Dark theme (token variant later) · marketing/landing pages · print/PDF styles of exported proposals (deterministic renderer's concern, not web UI) · mobile-first layouts (desktop-first per personas; sub-lg is degrade-gracefully only) · Hindi UI strings (PH2 — token stacks already carry Devanagari fallback).

## §H Design AC index

| AC | Screen | Check method | Verified by |
|----|--------|--------------|-------------|
| S1-D1 | S1 | DOM (failed login) | /design-review |
| S1-D2 | S1 | screenshot @ 768 | /design-review |
| S2-D1 | S2 | DOM + computed style | /design-review |
| S2-D2 | S2 | DOM (fixtures cleared) | /design-review |
| S3-D1 | S3 | DOM (EC-1 fixture) | /design-review |
| S3-D2 | S3 | DOM | /design-review |
| S4-D1 | S4 | DOM (low-confidence fixture) | /design-review |
| S4-D2 | S4 | DOM + computed style | /design-review |
| S4-D3 | S4 | DOM (EC-2 fixture) | /design-review |
| S5-D1 | S5 | DOM | /design-review |
| S5-D2 | S5 | DOM (corrigendum fixture) | /design-review |
| S6-D1 | S6 | DOM + computed style | /design-review |
| S6-D2 | S6 | DOM | /design-review |
| S7-D1 | S7 | DOM + computed style (fail fixture) | /design-review |
| S7-D2 | S7 | DOM | /design-review |
| S7-D3 | S7 | DOM (fuzzy fixture) | /design-review |
| S8-D1 | S8 | DOM (expiry fixture) | /design-review |
| S8-D2 | S8 | DOM | /design-review |
| S9-D1 | S9 | DOM (draft vs approved) | /design-review |
| S9-D2 | S9 | DOM | /design-review |
| S9-D3 | S9 | DOM (missing-evidence fixture) | /design-review |
| S10-D1 | S10 | DOM (blocker fixture) | /design-review |
| S10-D2 | S10 | DOM | /design-review |
| S10-D3 | S10 | DOM + computed style | /design-review |
| S11-D1 | S11 | DOM | /design-review |
| S11-D2 | S11 | DOM (low-data fixture) | /design-review |
| S11-D3 | S11 | DOM | /design-review |
| S12-D1 | S12 | DOM (audit fixture) | /design-review |
| S12-D2 | S12 | DOM | /design-review |
| S13-D1 | S13 | DOM | /design-review |
| GLB-D1 | all (sampled) | contrast calc + spot screenshots | /design-review |
| GLB-D2 | all (sampled) | screenshot + DOM @ 1024 | /design-review |
| GLB-D3 | verdict screens (sampled) | DOM | /design-review |

## §I Handoff block (machine-readable — schema in design-handoff-contract.md)

```json
{
  "schema": "design-spec/v1",
  "status": "approved",
  "approved_at": "2026-07-23T16:27:07Z",
  "prd": { "path": "tendercraft-PRD.md", "sha256": "915d25d1ee1ff5cba34be0db3a698f178dd720fb5d36045381bd3bba597d0838" },
  "mode": "mcp", "renders": true,
  "stitch": { "project_id": "4504009752110417749", "design_system": "assets/11021356356005444862" },
  "tokens_path": "design/tokens.json",
  "routes_derivation": "PRD has no routes section; routes derived from module UX flows and canonical here",
  "screens": [
    { "id": "S1", "route": "/login", "features": [], "acs_rendered": [],
      "states": { "default": "rendered", "loading": "specified", "empty": "n/a", "error": "rendered" },
      "reference": { "png": "design/reference/S1-login.png", "html": "design/reference/S1-login.html" },
      "source": "stitch", "design_acs": ["S1-D1","S1-D2"] },
    { "id": "S2", "route": "/dashboard", "features": ["E"], "acs_rendered": ["E-FR6"],
      "states": { "default": "rendered", "loading": "specified", "empty": "specified", "error": "specified" },
      "reference": { "png": "design/reference/S2-dashboard.png", "html": "design/reference/S2-dashboard.html" },
      "source": "stitch", "design_acs": ["S2-D1","S2-D2"] },
    { "id": "S3", "route": "/tenders/upload", "features": ["A"], "acs_rendered": ["A-FR1","A-AC4","EC-1","EC-7"],
      "states": { "default": "rendered", "loading": "rendered", "empty": "specified", "error": "rendered" },
      "reference": { "png": "design/reference/S3-upload.png", "html": "design/reference/S3-upload.html" },
      "source": "stitch", "design_acs": ["S3-D1","S3-D2"] },
    { "id": "S4", "route": "/tenders/:id/verify", "features": ["A"], "acs_rendered": ["A-FR4","A-AC5","EC-2"],
      "states": { "default": "rendered", "loading": "specified", "empty": "specified", "error": "rendered" },
      "reference": { "png": "design/reference/S4-verify.png", "html": "design/reference/S4-verify.html" },
      "source": "stitch", "design_acs": ["S4-D1","S4-D2","S4-D3"] },
    { "id": "S5", "route": "/tenders/:id", "features": ["A"], "acs_rendered": ["A-FR3"],
      "states": { "default": "rendered", "loading": "specified", "empty": "specified", "error": "rendered" },
      "reference": { "png": "design/reference/S5-tender-detail.png", "html": "design/reference/S5-tender-detail.html" },
      "source": "stitch", "design_acs": ["S5-D1","S5-D2"] },
    { "id": "S6", "route": "/profile", "features": ["C"], "acs_rendered": [],
      "states": { "default": "rendered", "loading": "specified", "empty": "specified", "error": "rendered" },
      "reference": { "png": "design/reference/S6-profile.png", "html": "design/reference/S6-profile.html" },
      "source": "stitch", "design_acs": ["S6-D1","S6-D2"] },
    { "id": "S7", "route": "/tenders/:id/analysis", "features": ["C"], "acs_rendered": ["C-FR4","C-FR5","C-AC4","C-AC5"],
      "states": { "default": "rendered", "loading": "specified", "empty": "specified", "error": "specified" },
      "reference": { "png": "design/reference/S7-analysis.png" },
      "source": "stitch", "design_acs": ["S7-D1","S7-D2","S7-D3"] },
    { "id": "S8", "route": "/library", "features": ["B"], "acs_rendered": [],
      "states": { "default": "rendered", "loading": "specified", "empty": "specified", "error": "rendered" },
      "reference": { "png": "design/reference/S8-library.png", "html": "design/reference/S8-library.html" },
      "source": "stitch", "design_acs": ["S8-D1","S8-D2"] },
    { "id": "S9", "route": "/proposals/:id", "features": ["B","E"], "acs_rendered": ["B-FR1","B-FR2","B-FR3","B-FR4"],
      "states": { "default": "rendered", "loading": "specified", "empty": "rendered", "error": "rendered" },
      "reference": { "png": "design/reference/S9-proposal-workspace.png", "html": "design/reference/S9-proposal-workspace.html" },
      "source": "stitch", "design_acs": ["S9-D1","S9-D2","S9-D3"] },
    { "id": "S10", "route": "/proposals/:id/export", "features": ["B","E"], "acs_rendered": ["B-AC4","B-AC5","B-FR5","E-AC2"],
      "states": { "default": "rendered", "loading": "specified", "empty": "n/a", "error": "rendered" },
      "reference": { "png": "design/reference/S10-export-gate.png", "html": "design/reference/S10-export-gate.html" },
      "source": "stitch", "design_acs": ["S10-D1","S10-D2","S10-D3"] },
    { "id": "S11", "route": "/proposals/:id/score", "features": ["D"], "acs_rendered": ["D-FR1","D-FR2","D-FR3","D-AC5"],
      "states": { "default": "rendered", "loading": "specified", "empty": "rendered", "error": "specified" },
      "reference": { "png": "design/reference/S11-score.png", "html": "design/reference/S11-score.html" },
      "source": "stitch", "design_acs": ["S11-D1","S11-D2","S11-D3"] },
    { "id": "S12", "route": "/settings", "features": ["E"], "acs_rendered": ["E-FR1","E-FR4","E-FR6"],
      "states": { "default": "rendered", "loading": "specified", "empty": "specified", "error": "specified" },
      "reference": { "png": "design/reference/S12-settings.png", "html": "design/reference/S12-settings.html" },
      "source": "stitch", "design_acs": ["S12-D1","S12-D2"] },
    { "id": "S13", "route": "/error", "features": [], "acs_rendered": ["EC-6"],
      "states": { "default": "rendered", "loading": "n/a", "empty": "n/a", "error": "rendered" },
      "reference": { "png": "design/reference/S13-error.png", "html": "design/reference/S13-error.html" },
      "source": "stitch", "design_acs": ["S13-D1"] }
  ],
  "components": [
    { "id": "C1", "name": "Sidebar nav (280px fixed)", "screens": ["S2","S3","S4","S5","S6","S7","S8","S9","S10","S11","S12"] },
    { "id": "C2", "name": "Dense data table (44px rows, sticky header)", "screens": ["S4","S5","S6","S7","S8","S10","S12"] },
    { "id": "C3", "name": "Criterion card (verbatim clause + anchor + verdict)", "screens": ["S4","S7","S9"] },
    { "id": "C4", "name": "Verdict/confidence chip", "screens": ["S4","S5","S7","S8","S9","S10"] },
    { "id": "C5", "name": "Citation chip", "screens": ["S6","S8","S9","S10"] },
    { "id": "C6", "name": "SLA deadline chip (escalation colors)", "screens": ["S2","S5","S7"] }
  ],
  "global_design_acs": ["GLB-D1","GLB-D2","GLB-D3"],
  "design_review_command": ".claude/commands/design-review.md"
}
```

## §J Consumption instructions

**agentic-project-scaffold** (patch in design-handoff-contract.md): wire `design/tokens.json` into the styling entrypoint (Tailwind theme extension or CSS variables), reference this spec from `docs/conventions.md`'s styling section, keep `design/reference/` in-repo, keep `/design-review`.

**project-planning-orchestrator (v1.1+)**: reads §I; UI tasks whose ACs render on S`k` get `design_ref: "S<k>"` (complexity floors at `med`); a design-system enabler task (tokens + C-components) is sequenced before any screen task.

**prd-to-ship**: zero-patch — its Phase 4.3 probes `/design-review`, which now exists and checks §H. Implementers: a task card carrying `design_ref` means open the reference render + tokens **before** writing UI code; the render is ground truth, the exported HTML is a styling crib and is never pasted into the codebase.

If this spec's sha256 ≠ the PRD on disk, the spec is stale: re-run stitch-ux-designer in re-design mode before consuming.
