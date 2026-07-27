# TenderCraft Evaluate — Officer Throughput · Product Requirements

**Extends [`tendercraft-evaluate-PRD.md`](tendercraft-evaluate-PRD.md). Does not replace it.**
Features F1–F13, entities E1–E13, journeys J1–J2, ENV-1–8 and FIX-1–8 remain in force exactly as
written there. This document adds F14–F28, E14–E26, journey J3, ENV-9–14 and FIX-9–16.

Source: seven P0 pain points recorded from procurement managers (TP1, TP6, TP11, TP17, TP32,
TP36, TP40). **Two of the seven require no new build** — see §1.2. This PRD covers the other five.

Surface: `apps/evaluate` + `services/evaluate-engine`. Buyer-side only. The F13 conflict-of-
interest wall applies to every line of it.

---

## Section 0 — Agent execution contract

- One milestone at a time (§5). Never pull later-milestone work.
- `TODO:` → stop and ask the human. `ASSUMPTION` → proceed and restate it in your summary.
- **AI reads and writes; code decides.** Unchanged from the base contract and extended here:
  document presence (F18) and outbound disclosure (F28) are pure functions in
  `evaluate/deterministic/` at 100% branch coverage. Attribution (F15), spec mapping (F20) and
  clause drafting (F22) are model *proposals* that a named human confirms. Model output that
  reaches a verdict, a qualification, a rank, or an outbound letter without a human in between
  is a defect, not a shortcut.
- **The compliance matrix never decides.** F19–F21 produce anchored evidence. Responsiveness
  stays owned by `deterministic/screening.py`; technical marks stay owned by named humans (F7).
- **Sealed-bid integrity survives bulk intake.** F14 is the widest new surface on F9. Reaching
  financial content before technical lock — by archive, by triage screen, by export, by error
  branch — is Sev-1.
- **The wall (F13) is architecture, not convention.** No import from `app/…`. Where the bidder
  product already solved something (the compliance matrix), copy the pattern by hand;
  `tools/check-wall.sh` fails the build on a stray import.
- Every outbound artifact is attributable to a named human.

---

## §1 Product

### 1.1 One sentence

Remove the manual labour that sits on either side of the evaluation the base product already
runs: authoring an unambiguous tender before it is published, and absorbing a pile of bids in
mixed formats after it closes.

### 1.2 Triage of the seven pain points

| TP | Pain | Verdict | Where |
|---|---|---|---|
| TP32 | Committees work in silos; Excel merging | **Already specified. Build nothing.** | F7 independent scoring + F8 aggregation, variance, consensus, quorum — base §5 M3 |
| TP36 | Evaluation reports compiled by hand | **Already specified. Build nothing.** | F11 report + F12 audit export — base §5 M5 |
| TP6 | Volume and format variety overwhelm officers | Extends shipped F5 | F14–F16, milestone N1 |
| TP11 | Manual checklisting of mandatory documents | New deterministic gate | F17–F18, milestone N2 |
| TP17 | Hundreds of pages read per bid to map offers to specs | New per-bid analyzer | F19–F21, milestone N3 |
| TP1 | RFPs poorly scoped; ambiguity causes re-tendering | New upstream journey | F22–F26, milestone N4 |
| TP40 | Award and regret notification not standardised | New; **overrides a base non-goal** | F27–F28, milestone N5 |

TP32 and TP36 are recorded here so nobody rebuilds them. If either is failing in practice it is a
defect against F7/F8/F11/F12, not a missing feature, and it is fixed there.

### 1.3 The problem this document adds

The base product begins at *"upload the RFP that was published"* and ends at *"evaluation marked
Concluded"*. Both boundaries are where the officer's manual work actually lives:

- **Before.** The RFP is drafted in Word from a reused template, circulated by email, and reviewed
  by the legal and procurement cells late — after the ambiguity is already baked in. The cost lands
  as re-tendering, scope disputes, and risk premiums in the prices received.
- **After.** Bids arrive as a folder of PDFs, scans, and spreadsheets. The officer opens each file,
  works out which bidder it belongs to, ticks a printed checklist for EMD and affidavits, then reads
  hundreds of pages per bid to find out what was actually offered — tracking all of it in Excel.
  Then, at the end, award and regret letters are written by hand and debriefs are ad hoc.

### 1.4 Users

Unchanged from base §1.3 — P1 procurement officer, P2 TEC member, P3 chair, P4 auditor — plus:

| ID | Persona | New to this document |
|---|---|---|
| **P5** | **Reviewer** — legal cell, finance, technical SME, procurement cell | Reviews and signs off a draft tender before publication (J3.7). Not a TEC member; a different person at a different stage. A user may hold both roles on different tenders. |

### 1.5 Success signals

| Signal | Target | Measured by |
|---|---|---|
| Time from "bids received" to "screening matrix readable" | −40% against the officer's own prior round | Timestamp between first file upload and first `/tenders/:id/screening` view |
| Files requiring manual attribution | ≤ 20% of uploaded files | `E15.confirmed_by IS NOT NULL AND proposed_bid_id IS NULL` share |
| Drafts published with zero open blocking findings | 100% (it is a hard gate) | F26 refuses otherwise |
| Drafts where a rule finding was raised and acted on before publication | ≥ 1 per draft, median | `E24` findings resolved vs dismissed |
| Qualitative | An officer stops keeping a parallel Excel tracker | Interview at the third tender |

---

## §2 Journey spine

### 2.1 What changes

J1 keeps every existing step and step number. Three sub-steps are **inserted** (J1.4a, J1.4b,
J1.5a) and one is **appended** (J1.11). No existing step is renumbered — base ACs reference them.

J3 is a new journey that runs **before** J1 and hands into it: publishing a draft creates the
tender with its framework pre-filled, so the officer lands at J1.2 with J1.1 already satisfied.
J1.1 (upload an RFP published elsewhere) remains supported forever — most authorities will have
published the tender before they ever meet this product.

### 2.2 J1 — amended primary journey

| Step | What the user does | Feature | Entry point | Lands on success |
|---|---|---|---|---|
| J1.1 | Create the tender; upload the published RFP | F2 | `/tenders` → "New tender" | `/tenders/:id/framework` |
| … | *J1.2 – J1.3 unchanged* | F3, F4 | | |
| **J1.4** | **Drop the whole received folder or ZIP; watch per-file progress** | **F14, F16** | Committee page CTA | `/tenders/:id/bids` |
| **J1.4a** | **Resolve the triage pile — files the engine could not confidently attribute** | **F15** | Amber banner on `/tenders/:id/bids` naming the count | `/tenders/:id/bids/triage` → back to `/tenders/:id/bids` at zero |
| **J1.4b** | **Review the mandatory-document checklist: bidders × required documents** | **F17, F18** | Auto-advance once triage is clear | `/tenders/:id/documents` |
| J1.5 | Review deterministic PQ screening; mark responsive / non-responsive with reason | F6 | Auto-advance from J1.4b | `/tenders/:id/screening` |
| **J1.5a** | **Read the per-bid compliance matrix: every technical requirement against what was offered, anchored to a page** | **F19, F20, F21** | "Compare offers" CTA on the screening matrix | `/tenders/:id/bids/:bidId/compliance` |
| J1.6 – J1.10 | *unchanged* | F7–F12 | | |
| **J1.11** | **Issue award and regret letters with per-bidder debrief summaries** | **F27, F28** | "Issue outcome" CTA on `/tenders/:id/result`, enabled only once the ranking is final | `/tenders/:id/award`; downloads per bidder |

**Activation moment is unchanged — J1.5.** These features make it arrive days sooner and with
fewer unknowns; they do not move it. J1.4b is the new *relief* moment (the checklist that used to
be a printed sheet fills itself in), but the screening matrix is still where the work visibly
collapses. Instrument both; optimise for J1.5 reached.

### 2.3 J3 — Authoring journey (new, P0)

Trigger: a requirement has been approved internally and a tender must be published. Today this
opens Word.

| Step | What the user does | Feature | Entry point | Lands on success |
|---|---|---|---|---|
| J3.1 | Start a draft — blank, from a past concluded tender, or from an authority template | F22 | `/drafts` → "New draft" | `/drafts/:id` |
| J3.2 | State scope, category (goods / works / consultancy) and estimated value | F22 | Auto-advance from J3.1 | `/drafts/:id` — checks begin firing |
| J3.3 | Build eligibility (PQ) criteria; rule findings appear against each as it is written | F22, F23, F24 | Draft hub section CTA | `/drafts/:id/criteria` |
| J3.4 | Build the technical rubric — marks, weights, QCBS ratio, qualifying marks | F22, F23 | Same page, second tab | `/drafts/:id/criteria` |
| J3.5 | Confirm the required-document list (EMD, forms, certifications, affidavits) | F22 | Draft hub section CTA | `/drafts/:id/documents` |
| J3.6 | Draft the narrative sections from the clause library | F22 | Draft hub section CTA | `/drafts/:id` |
| J3.7 | Send for review; named reviewers comment and sign off in parallel | F25 | "Send for review" on the draft hub | `/drafts/:id/review` |
| J3.8 | Resolve blocking findings and open comments | F23, F24, F25 | Blocker list on the draft hub | `/drafts/:id` with zero blockers |
| J3.9 | **Publish** — export the tender document and create the tender with its framework pre-filled | F26 | Primary CTA, disabled until J3.8 clears | `/tenders/:id/framework` — **this is J1.2** |

**J3 activation moment — J3.3, the first rule finding.** The moment a criterion the officer has
copied from the last tender for years is flagged as exceeding the GFR turnover ceiling, with the
rule cited, is the moment the product has said something the Word template never could.

### 2.4 First-run experience — deltas

The base first-run (`/tenders` empty state) is unchanged. Two new zero-data surfaces:

- **`/drafts` with zero drafts** renders `[data-empty-state]`: "Draft your first tender", one
  primary CTA to `/drafts/new`, and a three-step explainer (Describe the requirement → Build the
  criteria → Send for review). Never a bare table.
- **`/tenders/:id/bids` before any upload** keeps the dropzone as the hero and states the accepted
  formats and the archive limits (ENV-10/11) *before* the officer drags 400 MB at it.
- **A reviewer (P5) with nothing to review** sees "No drafts awaiting your review" plus who to
  contact — the same rule the base applies to an unassigned TEC member.

### 2.5 Navigation map — additions

| Route | Screen | Who | Notes |
|---|---|---|---|
| `/drafts` | Draft list | P1, P5 | New sidebar item, above Tenders |
| `/drafts/new` | Create draft | P1 | Blank · from past tender · from template |
| `/drafts/:id` | Draft hub — sections, blockers, publish | P1 | Publish CTA lives here, disabled with a named blocker count |
| `/drafts/:id/criteria` | PQ criteria + technical rubric, findings inline | P1 | |
| `/drafts/:id/documents` | Required-document list | P1 | Becomes E16 verbatim on publish |
| `/drafts/:id/review` | Reviewers, comments, sign-off status | P1, P5 | P5's home for this journey |
| `/tenders/:id/bids/triage` | Unattributed-file triage | P1 | Reachable only while the pile is non-empty; empty state says so and links back |
| `/tenders/:id/documents` | Document-presence matrix (bids × required documents) | P1, P3 | |
| `/tenders/:id/bids/:bidId/compliance` | Per-bid compliance matrix | P1, P2, P3 | Cross-bid view is a tab on the same route |
| `/tenders/:id/award` | Award, regret letters, debriefs | P1 | Unreachable until the ranking is final |

Every new route is reachable from an on-screen affordance named in §2.2/§2.3. None requires
typing a URL.

### 2.6 Screen state coverage

Base rule applies unchanged: default + loading (skeletons, never a bare spinner) + empty + error
on every screen; a blank region on a reachable state is a review failure. Two additional locked
states:

- `/tenders/:id/award` before the ranking is final renders an explicit "available once the
  ranking is final" panel naming what remains — never a 404, never a redirect that reads as an error.
- `/drafts/:id` after publication is read-only with a link to the created tender. A published
  draft is never editable; editing it would silently diverge from what bidders received.

### 2.7 Journey acceptance criteria

Run against **FIX-1 (the empty authority)** for J3, and **FIX-13** for the empty draft workspace.
No direct URL entry, no prior knowledge, no documentation.

- **J3-AC1 (happy):** A new officer signs in to an authority with zero drafts, reaches
  `/drafts/:id/review` with at least one criterion and one reviewer attached, using only on-screen
  affordances. *Verify: browser-verify.*
- **J3-AC2 (the publish gate):** With one blocking rule finding open and one required sign-off
  missing, the publish control is `disabled`, `[data-publish-blockers]` reads `2`, and
  `POST /api/drafts/:id/publish` returns `409 BLOCKING_FINDINGS`. *Verify: browser-verify + integration.*
- **J3-AC3 (the handoff):** Publishing a clean draft creates a tender, and the officer lands on
  `/tenders/:id/framework` with the criteria, weights, QCBS ratio and required-document list
  already populated from the draft — zero re-entry. *Verify: browser-verify + integration.*
- **J3-AC4 (abandon/resume):** An officer who closes the browser mid-draft returns to `/drafts/:id`
  and the section list names which sections are incomplete and which findings are open.
  *Verify: browser-verify.*
- **J1-AC6 (bulk happy):** From a locked framework, an officer uploads FIX-9 (one ZIP, 24 files,
  5 bidders) and reaches the document-presence matrix with every bidder attributed, using only
  on-screen affordances. *Verify: browser-verify.*
- **J1-AC7 (triage recovery):** FIX-9's two unattributable files surface as a named triage count on
  `/tenders/:id/bids`; the officer resolves them and the count reaches zero. No file is silently
  dropped and no file is silently attributed. *Verify: browser-verify.*
- **J1-AC8 (mid-journey failure recovery):** With the extraction service failing during a bulk
  upload, per-file rows show a named error and a retry; already-extracted files stay readable;
  re-uploading the same archive creates no duplicate bid. *Verify: browser-verify + integration.*
- **J1-AC9 (disclosure):** A regret letter generated for a losing bidder contains that bidder's own
  marks and rank, the winner's name and accepted price, and **no** other bidder's technical content
  and **no** per-member marks — asserted on the generated bytes, not on the screen.
  *Verify: integration.*

### 2.8 Traceability — zero orphans

| Feature | Journey steps | Entry point | Priority |
|---|---|---|---|
| F14 Bulk & archive intake | J1.4 | Committee page CTA → dropzone | P0 |
| F15 Auto-attribution & triage | J1.4a | Amber banner naming the count | P0 |
| F16 Format normalisation & OCR | J1.4 | — (runs inside F14; surfaced as per-file status) | P0 |
| F17 Required-document register | J1.4b, J3.5 | Auto-advance / draft hub CTA | P0 |
| F18 Presence gate | J1.4b | Auto-advance from J1.4a | P0 |
| F19 Bid offer extraction | J1.5a | — (runs inside F14; surfaced on the matrix) | P0 |
| F20 Requirement↔offer mapping | J1.5a | — (powers F21) | P0 |
| F21 Compliance matrix surface | J1.5a | "Compare offers" on the screening matrix | P0 |
| F22 Draft workspace & clause library | J3.1–J3.6 | `/drafts` → "New draft" | P0 |
| F23 Regulatory rule checks | J3.3, J3.4, J3.8 | Inline findings on the criteria page | P0 |
| F24 Past-tender signal | J3.3, J3.8 | Inline findings, same surface as F23 | P1 |
| F25 Parallel review & sign-off | J3.7, J3.8 | "Send for review" on the draft hub | P0 |
| F26 Publish | J3.9 | Primary CTA on the draft hub | P0 |
| F27 Award & debrief generation | J1.11 | "Issue outcome" on the result page | P1 |
| F28 Disclosure gate | — (invariant) | n/a — enforced, not navigated | P0 |

F16, F19, F20 and F28 have no independent entry point by design: three are pipeline stages
surfaced through another feature's screen, and F28 is a structural invariant verified by test —
the same exemption base F13 holds. Every other feature is reachable by clicking.

---

## §3 Non-goals

Base §3 non-goals remain in force **with one deliberate exception**, recorded below.

### 3.1 Override of a base non-goal — human decision, 2026-07-27

Base §3 reads: *"Bidder-facing outcome/regret letters — Outbound legal communication; separate
review. Deferred."* That row is **superseded** by this document.

| Field | Value |
|---|---|
| Overridden by | The human, 2026-07-27, in response to TP40 |
| Scope of override | Generation of award letters, regret letters and debrief summaries **inside the product**, gated by F28 |
| Still out of scope | Transmission. The product produces the document; the authority sends it through its own channel. No bidder identity, login, or inbound surface is created. |
| Condition | F28's disclosure filter is deterministic, 100% branch covered, and blocks generation rather than redacting after the fact |
| Reversible | Yes — remove milestone N5; nothing else depends on it |

### 3.2 New non-goals

| Non-goal | Why |
|---|---|
| CVC circulars, state procurement acts, GeM/CPPP portal rulepacks | v1 checks GFR 2017 + the 2022 Procurement Manuals only (D2). A half-implemented state rulepack is worse than none — an officer would trust it. |
| Physical / offline bid custody | v1 is digital and archive intake only (D5). Chain-of-custody for a sealed physical cover is a different compliance surface. |
| Email intake of bids | Sender authenticity on a sealed-bid process is a real attack, not a convenience gap. |
| Spreadsheet-manifest reconciliation | Deferred; F15's triage pile covers the same failure without importing the officer's tracker. |
| Crawling portals for comparable tenders | Past-tender signal is the authority's own concluded tenders only (D3). Third-party acquisition would trigger the discovery guardrails and a far larger surface. |
| Auto-award, auto-rejection, or a model deciding compliance | Unchanged from base. F21 informs; it never decides. |
| Editing a published draft | A published draft is what bidders received. Corrections are corrigenda against the tender, not edits to history. |
| Bidder-facing portal, login, or reply channel | The override in §3.1 is generation only. Becoming a bidder-facing system of record is not on the table. |

---

## §4 Decisions

Base §4 stands unchanged. Added here:

| # | Decision | Status | Value |
|---|---|---|---|
| D1 | Authoring output | **LOCKED** | Both a publishable tender document (DOCX) **and** the structured framework that pre-fills F3. Emitting only one of the two re-creates the manual re-keying this exists to remove. |
| D2 | Regulatory corpus | **LOCKED** | GFR 2017 + Manuals for Procurement of Goods / Works / Consultancy Services 2022. Rules live in a versioned rulepack file, not in code and never in a prompt. |
| D3 | Past-tender corpus | **LOCKED** | The authority's own concluded tenders only. No crawling, no external acquisition. |
| D4 | Review model | **LOCKED** | Parallel, not sequential. Named reviewers with required sign-off roles; publish blocked until satisfied. Sequential review is what makes the legal cell review late. |
| D5 | Physical bids | **LOCKED** | Out of scope in v1. |
| D6 | Bulk intake | **LOCKED** | Multi-file and ZIP upload with model-proposed attribution. No email intake, no manifest import. |
| D7 | OCR | **LOCKED** | Vision model through the existing `EVAL_MODEL_API_KEY`, invoked **only** on pages `ingest.split_legible` already reports illegible. No new vendor, no new credential, no new subscription. Per-tender page budget is `ENV-9` with a named failure, not an unbounded bill. |
| D8 | TP40 | **HUMAN-OVERRIDE 2026-07-27** | See §3.1. |
| D9 | Build order | **LOCKED** | N1 → N5 as in §5. Intake pain first: it lands inside a flow that already ships. |
| D10 | Route naming | **LOCKED** | `/tenders/*` and `/api/tenders/*`, matching the shipped app, migration `0003_rename.sql`, and base §11's glossary. Base §6.1's `/api/evaluations/*` table is stale; this document does not repeat the error. |
| D11 | Attribution authority | **LOCKED** | The model proposes a bidder; below `ENV-12` confidence, or on any ambiguity, the file goes to triage. A file is never attributed to a bidder without either high confidence **or** a human. |
| D12 | Presence vs adequacy | **LOCKED** | "Is the document there" is arithmetic (F18, deterministic). "Is it the right document, correctly executed" is a human judgement the product only assists. Conflating them is how an extraction miss disqualifies a bidder. |
| D13 | Rulepack severity | **LOCKED** | Findings are `blocking` or `advisory`. Blocking findings stop publication; advisory ones are dismissible with a recorded reason. A rule that cannot be justified as blocking is advisory. |

---

## §5 Build sequence

Vertical slices, continuing the base milestone series. Each makes a journey segment walkable.

| M | Scope | Journey segment | Exit criteria |
|---|---|---|---|
| **N1** | Bulk & archive intake, format normalisation, OCR fallback, attribution + triage | J1.4, J1.4a | F14-AC1..4, F15-AC1..4, F16-AC1..3, **J1-AC6, J1-AC7, J1-AC8** |
| **N2** | Required-document register + deterministic presence gate | J1.4b | F17-AC1..3, F18-AC1..4 |
| **N3** | Bid offer extraction, requirement↔offer mapping, compliance matrix surface | J1.5a | F19-AC1..3, F20-AC1..4, F21-AC1..3 |
| **N4** | Draft workspace, clause library, rulepack, past-tender signal, review + sign-off, publish | J3.1–J3.9 | F22-AC1..4, F23-AC1..5, F24-AC1..3, F25-AC1..4, F26-AC1..4, **J3-AC1..4** |
| **N5** | Award, regret and debrief generation behind the disclosure gate | J1.11 | F27-AC1..3, F28-AC1..4, **J1-AC9** |

N1 ships attribution triage in the same milestone as bulk upload. Shipping bulk intake without
triage produces a pile of silently mis-attributed files, which is worse than the Excel tracker it
replaces.

N2 depends on N1 (a register is checked against normalised files). N3 depends on N1. N4 depends on
nothing in N1–N3, but shipping it fourth means F17's register is already proven against real
tenders before F22 starts generating it. N5 depends on the base M4/M5 ranking being final.

---

## §6 Features

### F14 — Bulk & archive intake · P0 · complexity: high
*High: this is the widest new surface on the sealed-envelope gate (F9), and it is a file-upload
path handling untrusted archives.*

**Journey:** J1.4. Entry: committee page CTA → dropzone on `/tenders/:id/bids`. Precedes: J1.3
committee constitution. Lands on: `/tenders/:id/bids` with per-file rows. Cancel: partial uploads
are discarded; nothing half-ingested becomes a bid.

Drop a folder of files or a single ZIP. The engine unpacks, deduplicates by content hash, and
opens one per-file row with live status. **Envelope splitting from base F5 applies per file, not
per upload** — the split is what keeps F9 honest, and a bulk upload is just many chances to get
it wrong.

- **F14-AC1:** Uploading a ZIP of 24 mixed-format files (FIX-9) produces 24 rows on
  `/tenders/:id/bids`, each with a name, detected format, page count and status; zero console
  errors. *Verify: browser-verify.*
- **F14-AC2:** Financial content detected in a file attributed to a technical envelope is written
  to `bid_financials` (E7) and flagged, exactly as base F5-AC1 requires. No endpoint returns its
  contents before F9 unlock — asserted per file across the whole archive. *Verify: integration.*
- **F14-AC3:** Re-uploading the same archive creates no duplicate bid and no duplicate file row;
  identical content hashes are recognised and reported as already present.
  *Verify: integration.*
- **F14-AC4:** One file failing to parse never blocks the others; its row shows a named error and a
  retry control, and the remaining rows complete. *Verify: browser-verify.*

**Errors:**
- **F14-ERR1** archive exceeds `ENV-10` bytes or `ENV-11` entries → `413 ARCHIVE_TOO_LARGE`, naming
  the limit and the observed size. Never a silent truncation.
- **F14-ERR2** unsupported file type → `422 UNSUPPORTED_FORMAT` on that row only; the file is
  retained and listed, never discarded.
- **F14-ERR3** nested archive, path traversal entry (`../`), or symlink in the ZIP → rejected at
  unpack with a named error. An archive is untrusted input.
- **F14-ERR4** upload interrupted → partial rows are cleaned up; no orphan bid exists.

**Pitfalls:** double-submit creating duplicate bids (idempotency key, base F5-ERR3) · a ZIP is
untrusted input and a zip-bomb is a denial-of-service, not a curiosity · fanning OCR across every
page of every file at once will exhaust the model budget — bound it (F16).

### F15 — Auto-attribution & triage · P0 · complexity: high
*High: attributing a file to the wrong bidder corrupts an evaluation silently.*

**Journey:** J1.4a. Entry: amber banner on `/tenders/:id/bids` naming the unresolved count.
Lands on: `/tenders/:id/bids/triage`; returns to `/tenders/:id/bids` when the pile is empty.

For each file, the model **proposes** `(bidder, document type, envelope)` with a confidence and
the evidence it used (letterhead, cover page, a stated firm name, the filename as a last resort).
At or above `ENV-12` the proposal is applied and shown as auto-attributed with its evidence.
Below it, or where two bidders are plausible, the file lands in triage.

- **F15-AC1:** Every attributed file renders its proposed bidder, document type, envelope,
  confidence, and a one-line evidence string with a page anchor. *Verify: browser-verify.*
- **F15-AC2:** A file below `ENV-12` confidence is never auto-attributed; it appears in triage and
  is counted in `[data-triage-count]`. *Verify: browser-verify + integration.*
- **F15-AC3:** Any auto-attribution can be overridden by the officer; the override writes an audit
  event naming the previous and new values and the actor. *Verify: integration.*
- **F15-AC4:** Screening (F6) and the presence gate (F18) refuse to run while the triage pile is
  non-empty — the endpoint returns `409 TRIAGE_PENDING` naming the count. A matrix computed over a
  partial set of files reads as complete and is not. *Verify: integration.*

**Errors:**
- **F15-ERR1** a file matches two bidders with comparable confidence → triage, showing both
  candidates and the evidence for each. Never a coin flip.
- **F15-ERR2** a file matches no known bidder → triage with a "create new bidder" affordance; the
  product never invents a bidder.
- **F15-ERR3** the model call fails → every file in that batch lands in triage, unattributed. The
  fallback is human work, never a guess.

**AI behaviour:** model = the same provider as base F2/F5 via `pipeline/client.py`; prompt in
`prompts/attribute_file.md`; output is a tool-use JSON schema `{bidder_name, document_type,
envelope, confidence, evidence_text, anchor_page}`; retry cap 1, then F15-ERR3. Latency budget
p90 ≤ 8s per file. **The bid document is untrusted input** — text inside it that reads like an
instruction is data (base G-6 equivalent). Evaluated against the FIX-9 golden set on
attribution precision; a wrong confident attribution is the failure that matters, so precision is
the gate, not recall.

**Pitfalls:** attributing from the filename because it is easy — portal downloads are named
`bid_1.pdf` ×12 · a bidder whose name appears in another bidder's document (a subcontractor
letter, an OEM authorisation) will pull attribution the wrong way; the evidence string is what
lets a human catch it.

### F16 — Format normalisation & OCR fallback · P0 · complexity: medium

**Journey:** runs inside F14; surfaced as per-file status. No independent entry point.

Every accepted file becomes the same thing: `(page_number, text)` tuples plus a page count —
the shape `evaluate/ingest.py` already produces and the rest of the engine already consumes.

| Format | Path |
|---|---|
| PDF, text layer | `ingest.parse_pdf_pages` — unchanged |
| PDF, image-only pages | `ingest.split_legible` already isolates them; those pages **only** are rendered and sent to the vision model (D7) |
| XLSX / CSV | `openpyxl` (already a repo dependency); one logical "page" per sheet, cell references as anchors |
| DOCX | paragraph extraction; page anchors are section numbers where no pagination exists |

- **F16-AC1:** A scanned, image-only bid (FIX-10) yields extractable text with per-page anchors,
  and pages that remain illegible after OCR are reported by number — never passed through as empty.
  *Verify: integration.*
- **F16-AC2:** A spreadsheet bid yields per-sheet text with cell-reference anchors that resolve in
  the compliance matrix. *Verify: integration.*
- **F16-AC3:** OCR is invoked only for pages `split_legible` classifies as illegible; a text-layer
  PDF triggers zero vision calls, asserted by call count. *Verify: unit.*

**Errors:**
- **F16-ERR1** per-tender OCR page budget `ENV-9` exhausted → remaining pages are marked
  `ocr_budget_exceeded` with a named banner and a per-tender override for the officer. The run
  never silently degrades and never silently bills.
- **F16-ERR2** OCR returns empty for a page → the page is reported illegible, exactly as today. The
  base rule holds: *a bidder disqualified because page 14 was a photograph is the worst outcome
  this product can produce.*
- **F16-ERR3** password-protected or corrupt file → named error on that row, retained for a human.

**AI behaviour:** vision model via the existing client; prompt `prompts/ocr_page.md`; output
schema `{page_text, legible: bool}`; retry cap 1 then F16-ERR2. Cost ceiling is structural: only
already-illegible pages, capped by `ENV-9`. Evaluated on a golden set of scanned Indian tender
pages for character-level recall — never on exact text equality.

### F17 — Required-document register · P0 · complexity: medium

**Journey:** J1.4b (consumed) and J3.5 (authored). Entry: auto-advance from J1.4a; draft hub CTA.

The checklist as data. For a tender created by J1.1, the register is proposed from the tender's own
criteria and confirmed by the officer. For a tender published from a draft (F26), the register is
carried over verbatim — **the officer never builds it twice**, which is the whole reason TP1 and
TP11 are in the same document.

Each entry: label, whether it is mandatory, the criterion it derives from (nullable), the accepted
evidence types, and whether an original is required at submission.

- **F17-AC1:** A tender with 18 required documents (FIX-11) renders all 18 with mandatory flags and,
  where derived, a link to the source criterion with a page anchor. *Verify: browser-verify.*
- **F17-AC2:** The register is editable until the first bid file is attributed, and read-only
  afterwards; the endpoint returns `409 REGISTER_FROZEN`. Changing the checklist mid-screening
  changes who qualifies. *Verify: integration.*
- **F17-AC3:** A tender published from a draft has a register identical to the draft's, with no
  officer action. *Verify: integration.*

**Errors:** **F17-ERR1** no documents derivable from the criteria → the register starts empty with
a named prompt and manual-add, never a fabricated list · **F17-ERR2** duplicate label → rejected
with `422 DUPLICATE_REQUIREMENT`.

### F18 — Document-presence gate · P0 · complexity: high
*High: a deterministic gate whose output feeds a decision that removes a bidder.*

**Journey:** J1.4b. Entry: auto-advance from J1.4a. Lands on: `/tenders/:id/documents`.

New module `evaluate/deterministic/presence.py`, **no model in the path**, 100% branch coverage.
It answers exactly one question per (bid × required document): is a file attributed to this bidder
that matches this requirement's accepted types?

Verdicts mirror `screening.Verdict` deliberately:

| Verdict | Meaning |
|---|---|
| `PRESENT` | An attributed file matches the requirement's accepted evidence types |
| `MISSING` | No attributed file matches, and every file for this bidder is attributed (no ambiguity remains) |
| `NEEDS_REVIEW` | A file plausibly matches but the type is uncertain, or this bidder still has files in triage |

- **F18-AC1:** Verdicts are computed by `presence.py` with zero model calls in the path.
  *Verify: unit — 100% branch.*
- **F18-AC2:** The matrix renders bidders × required documents, every cell carrying its verdict and,
  where present, the file and page it matched. *Verify: browser-verify.*
- **F18-AC3:** `MISSING` never auto-rejects a bid. It surfaces as a proposed finding; removing a
  bidder still runs through base F6-AC3 (written reason, audit, report). *Verify: integration.*
- **F18-AC4:** A bidder with any file still in triage yields `NEEDS_REVIEW`, never `MISSING`, for
  every unmatched requirement. *Verify: unit.*

**Errors:** **F18-ERR1** the register is empty → the screen states that no documents are required
rather than rendering an empty grid · **F18-ERR2** a file matches two requirements → matched
against both, counted once, flagged for review · **F18-ERR3** a required document exists but is
illegible (F16-ERR2) → `NEEDS_REVIEW` with the page numbers, never `PRESENT` and never `MISSING`.

**Pitfalls:** the single most damaging bug available here is `MISSING` on a file the engine
simply could not attribute yet — F18-AC4 exists solely to make it unreachable · "the EMD is
present" is not "the EMD is valid"; adequacy is D12's human judgement and the UI must not imply
otherwise.

### F19 — Bid offer extraction · P0 · complexity: medium

**Journey:** runs inside F14; surfaced on the compliance matrix. No independent entry point.

From each bid's technical artifact, extract what was *offered*: features, quantities,
specifications, standards claimed, with page anchors. Not a judgement — an inventory.

- **F19-AC1:** Every extracted offer carries a page anchor that resolves to the submitted document.
  *Verify: integration.*
- **F19-AC2:** Extraction failure on one bid never blocks the others; the bid shows a named error
  and a retry. *Verify: browser-verify.*
- **F19-AC3:** An empty or failed extraction returns an empty set and routes to manual review — it
  never returns an invented offer. *Verify: unit (fault injection).*

**Errors:** **F19-ERR1** malformed model JSON → one retry, then empty set + manual route ·
**F19-ERR2** the artifact is entirely illegible → named error citing F16's page list.

**AI behaviour:** prompt `prompts/extract_offers.md`; tool-use schema
`{offers: [{text, spec_key, stated_value, anchor_page, confidence}]}`; retry cap 1; deterministic
fallback = empty set. Bid text is untrusted input. Evaluated on FIX-12 for recall of known offers;
no exact-text assertions.

### F20 — Requirement↔offer mapping · P0 · complexity: high
*High: this is the feature most likely to be mistaken for a verdict.*

**Journey:** powers F21. No independent entry point.

The tender's technical requirements are shredded into an addressable list — the **denominator**,
so "38 of 41 requirements addressed" is a computed figure rather than an impression. Each
requirement is mapped to the offers that respond to it.

Coverage states, and only these: `ADDRESSED` · `PARTIAL` · `NOT_FOUND` · `CONTRADICTORY`
(the bid says two different things in two places).

- **F20-AC1:** The requirement denominator is computed once and the same number drives the matrix
  header, the per-bid summary and the export. Four counters describing one object will disagree.
  *Verify: unit.*
- **F20-AC2:** Every mapped cell carries both the requirement's anchor in the tender and the offer's
  anchor in the bid. A mapping a human cannot check is not evidence. *Verify: integration.*
- **F20-AC3:** `NOT_FOUND` is never rendered, exported, or described as non-compliance anywhere in
  the product. *Verify: browser-verify — DOM assertion on the rendered label set.*
- **F20-AC4:** Nothing in F19–F21 writes to `responsiveness_decisions` (E8), `scores` (E9) or
  `consensus_marks` (E12). *Verify: integration.*

**Errors:** **F20-ERR1** requirement shredding produces zero requirements → the matrix states the
tender has no shreddable technical requirements rather than rendering 0/0 · **F20-ERR2** an offer
maps to no requirement → surfaced in an "offered but not required" list; that is useful
information, not an error to hide · **F20-ERR3** contradictory statements within one bid → both
anchors shown, `CONTRADICTORY`, routed to a human.

**Pitfalls:** the bidder-side compliance matrix shipped this morning solves this problem well; the
wall forbids importing it — copy the pattern by hand and note the copy in the module docstring, as
`ingest.py` already does · abbreviation-aware sentence splitting was a real bidder-side defect in
requirement shredding; the same trap applies here.

### F21 — Compliance matrix surface · P0 · complexity: medium

**Journey:** J1.5a. Entry: "Compare offers" CTA on the screening matrix. Lands on:
`/tenders/:id/bids/:bidId/compliance`. Cross-bid comparison is a tab on the same route.

- **F21-AC1:** Per-bid view renders every requirement with its coverage state, the mapped offer
  text, and both anchors; the header states `n of N addressed` using F20-AC1's single figure.
  *Verify: browser-verify.*
- **F21-AC2:** Cross-bid view renders requirements × bids with a coverage state per cell; the table
  scrolls inside its own container and the page never scrolls horizontally.
  *Verify: browser-verify @ 1024.*
- **F21-AC3:** Every cell exposes a rationale affordance and a source link; neither is ever a
  verdict chip reusing the reserved Pass/Fail/Needs-review semantics. *Verify: browser-verify.*

**Errors:** **F21-ERR1** extraction still running → per-bid skeletons with a stage note, never a
bare spinner and never an empty grid · **F21-ERR2** a bid marked non-responsive → matrix remains
readable and labelled as such; evidence does not disappear because a bidder was excluded.

### F22 — Draft workspace & clause library · P0 · complexity: high
*High: it authors the document a public tender is conducted under.*

**Journey:** J3.1–J3.6. Entry: `/drafts` → "New draft". Lands on `/drafts/:id`. Cancel: a draft is
retained; nothing is published by leaving.

A structured draft — metadata (category, estimated value, timeline), PQ criteria, technical
rubric, required documents, and narrative sections — with an authority-scoped clause library.
Clauses come from three places, all recorded: the authority's own concluded tenders (D3), clauses
the authority has saved, and starter clauses shipped with the rulepack.

- **F22-AC1:** Starting a draft from a concluded tender copies its criteria, rubric and required
  documents, each marked with its origin tender. *Verify: browser-verify.*
- **F22-AC2:** Every inserted clause carries provenance — source, who saved it, when — visible in
  the editor. An unattributed clause in a tender document is exactly the reused-template problem
  this feature exists to end. *Verify: browser-verify.*
- **F22-AC3:** Clause library reads are scoped to the authority by RLS; a second authority's
  clauses never appear. *Verify: integration — isolation suite.*
- **F22-AC4:** A draft's weights, QCBS ratio and qualifying marks are validated on save; weights
  not summing to 100 return `422 WEIGHTS_INVALID` — the same code base F3 uses.
  *Verify: integration.*

**Errors:** **F22-ERR1** estimated value absent → value-dependent rule checks report
`not_evaluated` with the reason, never silently pass · **F22-ERR2** concurrent edits by two
officers → last-write-wins with a visible "edited by X" marker; no silent overwrite ·
**F22-ERR3** model-assisted clause drafting fails → the section stays editable and empty with a
named error; the officer is never blocked from writing it themselves.

**AI behaviour:** clause drafting is model-assisted and always human-edited. Prompt
`prompts/draft_clause.md`; the model may propose prose but **may not propose a numeric threshold,
a value, or a date** — those come from the officer or the rulepack. Evaluated on schema validity
and on the absence of invented figures, never on exact text.

**Pitfalls:** a model quoting the authority's own uploaded template is citing, not hallucinating —
an unfilled placeholder (`[Insert Designation]`) propagates into a published tender with
provenance attached, which makes it look checked. Detect template markers on clause import.

### F23 — Regulatory rule checks · P0 · complexity: high
*High: a blocking gate on publication of a legal instrument.*

**Journey:** J3.3, J3.4, J3.8. Entry: findings render inline against the criterion that caused
them, on `/drafts/:id/criteria`, and aggregate on the draft hub.

Deterministic checks over the D2 corpus, in `evaluate/deterministic/rulepack.py` reading a
versioned rulepack file (`ENV-13`). **No model in this path.** Each rule states its citation, its
severity (D13), and what would satisfy it.

Starter rule set (each with a GFR/Manual citation carried in the rulepack, not in code):

| Rule | Check | Severity |
|---|---|---|
| R1 | Annual-turnover requirement ≤ 2× the estimated annual value | blocking |
| R2 | Bid submission window meets the minimum for the tender's value and type | blocking |
| R3 | Two-envelope (technical + financial) used above the prescribed threshold | blocking |
| R4 | No brand, make or model named without "or equivalent" | blocking |
| R5 | Similar-work experience requirement not disproportionate to the estimated value | blocking |
| R6 | EMD within the prescribed band; MSE / startup exemptions stated | blocking |
| R7 | Pre-bid meeting scheduled where required, and before the deadline by the prescribed margin | advisory |
| R8 | Weights sum to 100; qualifying marks stated; QCBS ratio within the permitted band | blocking |
| R9 | Every evaluation criterion states its evaluation method | blocking |
| R10 | No criterion is stated in the narrative but absent from the rubric | advisory |

- **F23-AC1:** Findings are produced by `rulepack.py` with zero model calls in the path.
  *Verify: unit — 100% branch.*
- **F23-AC2:** FIX-14 (three seeded violations) produces exactly three findings, each naming the
  rule, its citation, the offending value, and what would satisfy it. *Verify: unit + browser-verify.*
- **F23-AC3:** A blocking finding disables the publish control and increments
  `[data-publish-blockers]`. *Verify: browser-verify.*
- **F23-AC4:** An advisory finding can be dismissed only with a written reason, which is recorded
  in the audit trail and appears in the draft's history. *Verify: integration.*
- **F23-AC5:** The rulepack version used is stamped on the draft at publication, so a tender can be
  re-checked years later against the rules that actually applied. *Verify: integration.*

**Errors:** **F23-ERR1** rulepack file missing or unparseable → **fail fast at startup with a named
error**; a silently rule-less draft workspace is the worst possible degradation ·
**F23-ERR2** a rule cannot evaluate for want of a value (F22-ERR1) → `not_evaluated`, shown with
the missing input named; never treated as a pass · **F23-ERR3** rulepack version changes between
draft and publish → the draft is re-checked and the officer is told what changed.

### F24 — Past-tender signal · P1 · complexity: medium

**Journey:** J3.3, J3.8. Entry: same inline findings surface as F23, visually distinguished as
advisory evidence rather than rule findings.

Over the authority's own concluded tenders (D3), surface criteria that historically suppressed
competition:

| Signal | Trigger |
|---|---|
| S1 | This criterion (or a close match) eliminated a majority of bidders in a prior tender |
| S2 | A prior tender with this criteria set received fewer than three responsive bids |
| S3 | A clause present in a tender that was subsequently re-tendered |

- **F24-AC1:** Every signal names the specific prior tenders it is drawn from, with links.
  An unattributable statistic is not evidence. *Verify: browser-verify.*
- **F24-AC2:** With fewer than `ENV-14` concluded tenders in the authority (FIX-13, zero concluded),
  the panel renders
  `[data-signal-suppressed]` and **no numeric claim appears in the DOM**. A confident number from
  two data points is a fabrication. *Verify: browser-verify + unit.*
- **F24-AC3:** Signals are advisory only and never block publication. *Verify: integration.*

**Errors:** **F24-ERR1** no concluded tenders → suppressed state with an explanation, never an
empty panel · **F24-ERR2** criteria not comparable across tenders → the signal is omitted rather
than stretched.

**Pitfalls:** the bidder-side score estimator taught this exact lesson — prediction and
measurement must stay separate functions, and suppression must be impossible to escape.

### F25 — Parallel review & sign-off · P0 · complexity: medium

**Journey:** J3.7, J3.8. Entry: "Send for review" on the draft hub. Lands on `/drafts/:id/review`.
This is P5's home.

Reviewers are added by role; `ENV-15` names the roles whose sign-off is required. All reviewers
see the draft at the same time — sequential routing is why the legal cell reviews late.

- **F25-AC1:** Every reviewer sees the draft simultaneously on being added; none waits on another.
  *Verify: integration.*
- **F25-AC2:** Comments are anchored to a section or a criterion and render at that anchor.
  *Verify: browser-verify.*
- **F25-AC3:** Publish is blocked while any required-role sign-off is missing;
  `POST /api/drafts/:id/publish` returns `409 SIGNOFF_MISSING` naming the roles.
  *Verify: integration.*
- **F25-AC4:** A sign-off records actor, role and timestamp, and is invalidated by any subsequent
  substantive edit to the draft — the reviewer is asked again. A sign-off on a document that then
  changed is not a sign-off. *Verify: integration.*

**Errors:** **F25-ERR1** a required-role reviewer is never added → the blocker names the missing
role, not a generic count · **F25-ERR2** a reviewer is removed after signing → their sign-off is
retained in history and no longer counts toward the gate · **F25-ERR3** all reviewers sign but
blocking findings remain → publish stays blocked; F23 and F25 are independent gates.

### F26 — Publish · P0 · complexity: high
*High: irreversible, and it creates the object the entire base product operates on.*

**Journey:** J3.9. Entry: primary CTA on the draft hub, disabled until J3.8 clears. Lands on
`/tenders/:id/framework` — which is base J1.2.

Publishing does three things atomically: renders the tender document, creates the tender with its
criteria, rubric, weights, QCBS ratio, qualifying marks and required-document register
pre-populated, and freezes the draft read-only with the rulepack version stamped.

- **F26-AC1:** Publishing a clean draft returns `201` and creates a tender whose criteria and
  register match the draft exactly, field for field. *Verify: integration.*
- **F26-AC2:** The exported document contains every criterion and required document present in the
  framework — the published paper and the structured framework cannot disagree.
  *Verify: integration.*
- **F26-AC3:** Publishing with any blocking finding or missing sign-off returns `409` with
  `BLOCKING_FINDINGS` or `SIGNOFF_MISSING` and creates nothing. Partial publication is impossible.
  *Verify: integration.*
- **F26-AC4:** A published draft is read-only; every mutation endpoint returns
  `409 DRAFT_PUBLISHED`. *Verify: integration.*

**Errors:** **F26-ERR1** document rendering fails after the tender row is created → the whole
transaction rolls back; there is no tender without its document · **F26-ERR2** double-click on
publish → idempotency key; exactly one tender · **F26-ERR3** the draft references a clause whose
library entry was deleted → publication proceeds using the snapshot embedded in the draft; a
library edit never rewrites a document already drafted.

### F27 — Award & debrief generation · P1 · complexity: medium

**Journey:** J1.11. Entry: "Issue outcome" on `/tenders/:id/result`, enabled only when the ranking
is final. Lands on `/tenders/:id/award`.

Generates, per bidder, an award or regret letter plus a debrief summary drawn from evaluation data
already in the system — no re-keying, no copy-paste from spreadsheets.

- **F27-AC1:** With a final ranking (FIX-16), one letter is generated per bidder: award for rank 1,
  regret for the rest, each naming the tender, the bidder, and the outcome.
  *Verify: integration.*
- **F27-AC2:** Every figure in a letter is transcluded from stored evaluation data, not authored by
  the model; the model writes only connective prose. *Verify: integration.*
- **F27-AC3:** Generation before the ranking is final returns `409 RESULT_NOT_FINAL` and produces
  zero bytes. *Verify: integration.*

**Errors:** **F27-ERR1** an unresolved tie → blocked, deferring to base F10-AC3/AC4; the product
never names a winner the humans have not · **F27-ERR2** model failure → the deterministic skeleton
(outcome, marks, rank) still renders; only the prose is absent, marked as such.

**AI behaviour:** prompt `prompts/debrief.md`; the model receives **only** the fields F28 has
already cleared for that recipient — the filter runs before generation, not after. It may not
author a number, a rank, or a price. Evaluated on the absence of disclosed-but-forbidden fields,
not on prose quality.

### F28 — Disclosure gate · P0 · complexity: high
*High: the only path in either product where evaluation data is packaged for someone outside the
authority.*

**Journey:** none — a structural invariant, verified by test. The same exemption base F13 holds.

New module `evaluate/deterministic/disclosure.py`, **no model in the path**, 100% branch coverage.
A pure function from (recipient bidder, tender state) to the exact field set permitted.

| Permitted to a losing bidder | Never permitted |
|---|---|
| Their own criterion-level marks and rationale | Any other bidder's marks, rationale or technical content |
| Their own rank and total | Individual TEC members' marks, names, or deference rates |
| Their own responsiveness verdicts and reasons | Committee deliberation, consensus notes, variance flags |
| The winner's name and accepted price | Any other bidder's price, other than the accepted one |
| The published criteria and weights | COI declarations |

- **F28-AC1:** The permitted field set is computed by `disclosure.py` with zero model calls.
  *Verify: unit — 100% branch.*
- **F28-AC2:** A generated regret letter contains no other bidder's technical content and no
  per-member marks — asserted on the produced bytes. *Verify: integration.*
- **F28-AC3:** The filter runs **before** generation; forbidden fields never enter the model
  prompt. Redacting after generation is not a gate. *Verify: integration.*
- **F28-AC4:** Requesting a letter for a bidder in a tender whose ranking is not final, or from a
  different authority, returns `409 DISCLOSURE_BLOCKED` / `404`. *Verify: integration.*

**Errors:** **F28-ERR1** an unrecognised field reaches the filter → **denied by default** and
logged. An allowlist that fails open is not an allowlist · **F28-ERR2** the tender is under
challenge or archived → generation blocked with a named state.

**Pitfalls:** the temptation to "just include the comparison table so the bidder understands" —
that table is every other bidder's technical evaluation · a debrief is the artifact most likely
to be read by a lawyer; every figure in it must be traceable to an audit row.

---

## §6.1 API surface — additions

Inherited envelope `{ ok, data, error: { code, message } }` on every response including errors.
Binary endpoints return bytes on 2xx and the envelope on every error path. Routes are `/api/tenders/*`
per D10.

| Method | Endpoint | Feature | Notable statuses |
|---|---|---|---|
| POST | `/api/tenders/{id}/bids/bulk` | F14 | 202 · 413 `ARCHIVE_TOO_LARGE` · 422 `UNSUPPORTED_FORMAT` |
| GET | `/api/tenders/{id}/intake` | F14, F15 | 200 — per-file rows with status and attribution |
| POST | `/api/tenders/{id}/intake/{fileId}/retry` | F14 | 202 · 409 `FILE_NOT_FAILED` |
| PUT | `/api/tenders/{id}/intake/{fileId}/attribution` | F15 | 200 · 422 `BIDDER_REQUIRED` |
| GET | `/api/tenders/{id}/documents` | F17, F18 | 200 · 409 `TRIAGE_PENDING` |
| PUT | `/api/tenders/{id}/documents/register` | F17 | 200 · 409 `REGISTER_FROZEN` · 422 `DUPLICATE_REQUIREMENT` |
| PUT | `/api/tenders/{id}/documents/{reqId}/{bidId}` | F18 | 200 · 422 `REASON_REQUIRED` |
| GET | `/api/tenders/{id}/bids/{bidId}/compliance` | F20, F21 | 200 · 409 `EXTRACTION_PENDING` |
| POST | `/api/tenders/{id}/compliance` | F19, F20 | 202 |
| POST | `/api/drafts` | F22 | 201 |
| GET · PUT | `/api/drafts/{id}` | F22 | 200 · 409 `DRAFT_PUBLISHED` · 422 `WEIGHTS_INVALID` |
| GET | `/api/drafts/{id}/checks` | F23, F24 | 200 |
| POST | `/api/drafts/{id}/checks/{findingId}/dismiss` | F23 | 200 · 422 `REASON_REQUIRED` · 409 `FINDING_BLOCKING` |
| POST | `/api/drafts/{id}/review` | F25 | 201 · 422 `ROLE_REQUIRED` |
| POST | `/api/drafts/{id}/review/signoff` | F25 | 200 · 409 `FINDINGS_OPEN` · 403 `NOT_REVIEWER` |
| GET | `/api/drafts/{id}/document` | F26 | 200 (bytes) |
| POST | `/api/drafts/{id}/publish` | F26 | 201 · 409 `BLOCKING_FINDINGS` · 409 `SIGNOFF_MISSING` · 409 `DRAFT_PUBLISHED` |
| POST | `/api/tenders/{id}/award` | F27 | 200 · 409 `RESULT_NOT_FINAL` · 409 `TIE_UNRESOLVED` |
| GET | `/api/tenders/{id}/award/{bidId}/letter` | F27, F28 | 200 (bytes) · 409 `DISCLOSURE_BLOCKED` |

Error codes are `SCREAMING_SNAKE`; the web UI switches on `code`, never on message text.

---

## §6.2 Known pitfalls by feature

| Feature | Pitfall | Control |
|---|---|---|
| F14 | A ZIP is untrusted input — zip bombs, `../` traversal, symlinks | Bounded unpack (`ENV-10/11`), entry-name validation, F14-ERR3 |
| F14 | Bulk upload multiplies every chance to mis-split an envelope | Split runs per file; F14-AC2 asserts across the whole archive |
| F14 | OCR fanned across every page of every file exhausts the model budget | Only illegible pages, capped by `ENV-9`, F16-AC3 asserts the call count |
| F15 | Attribution from the filename — portal downloads are `bid_1.pdf` ×12 | Evidence string with a page anchor is mandatory on every attribution |
| F15 | A subcontractor letter or OEM authorisation pulls attribution to the wrong firm | Below-threshold → triage; the evidence string is what lets a human catch it |
| F15 | A matrix computed while files are still unattributed reads as complete | F15-AC4: screening and presence return `409 TRIAGE_PENDING` |
| F17 | The register edited mid-screening changes who qualifies, retroactively | Frozen at first attribution (F17-AC2) |
| F18 | `MISSING` on a file the engine could not yet attribute → a wrongful disqualification | `NEEDS_REVIEW` wins whenever triage is non-empty (F18-AC4) |
| F18 | "Present" read as "valid" | D12; the UI names presence only, adequacy stays a human judgement |
| F20 | The matrix mistaken for a compliance verdict | F20-AC3 bans the label; F20-AC4 asserts it writes to no decision table |
| F20 | Abbreviation-blind sentence splitting shreds requirements wrongly | Known bidder-side defect; the same splitter fix applies here |
| F20 | Four counters describing one denominator will disagree | One function computes the figure and its breakdown (F20-AC1) |
| F22 | An unfilled template marker (`[Insert Designation]`) publishes with provenance attached, so it looks checked | Template-marker detection on clause import |
| F23 | A missing rulepack silently yields a rule-less workspace | Fail fast at startup (F23-ERR1) |
| F23 | Rules drifting into prompts, so the model decides legality | `deterministic/rulepack.py`, import check in CI, 100% branch coverage |
| F24 | A confident statistic from two prior tenders | Suppression below `ENV-14`, with no number in the DOM (F24-AC2) |
| F25 | A sign-off surviving a later substantive edit | Invalidated on edit (F25-AC4) |
| F26 | A tender created without its document, or a document without its tender | Single transaction; F26-ERR1 rolls back |
| F26 | A library edit rewriting an already-drafted document | Clause snapshot embedded at insert (F26-ERR3) |
| F27 | The model authoring a figure in a legal letter | Transclusion only (F27-AC2); the model writes prose, never numbers |
| F28 | Redaction after generation instead of filtering before it | F28-AC3 asserts the ordering |
| F28 | An allowlist that fails open on an unrecognised field | Deny by default and log (F28-ERR1) |

---

## §6.3 Core data shapes

```jsonc
// E14 bid_files — one row per file, whatever the archive it arrived in.
{ "id": "bf_01H...", "authority_id": "au_01H...", "tender_id": "tn_01H...",
  "filename": "Technical_Bid_Vol1.pdf", "sha256": "9f2c...", "mime": "application/pdf",
  "source_archive_id": "ar_01H...", "page_count": 214,
  "status": "extracted",              // received | normalising | extracted | failed
  "ocr_pages": [12, 13, 88], "illegible_pages": [] }

// E15 file_attributions — the proposal and the confirmation are different fields, on purpose.
{ "id": "fa_01H...", "file_id": "bf_01H...",
  "proposed_bid_id": "bd_01H...", "proposed_document_type": "technical_bid",
  "proposed_envelope": "technical", "confidence": 0.91,
  "evidence_text": "Kaveri Networks Pvt Ltd — Technical Bid", "anchor_page": 1,
  "confirmed_bid_id": null, "confirmed_by": null, "confirmed_at": null }

// E17 document_presence — mirrors ScreeningCell deliberately.
{ "bid_id": "bd_01H...", "requirement_id": "rq_01H...",
  "verdict": "needs_review",          // present | missing | needs_review
  "matched_file_id": null, "anchor_page": null,
  "reason": "bidder has 2 files awaiting attribution" }

// E20 compliance_cells — evidence, never a verdict.
{ "requirement_id": "sr_01H...", "bid_id": "bd_01H...",
  "coverage": "partial",              // addressed | partial | not_found | contradictory
  "offer_text": "99.5% uptime SLA, 24x7 NOC",
  "requirement_anchor_page": 34, "offer_anchor_page": 61, "confidence": 0.78 }

// E24 rule_findings — a finding names what would satisfy it, or it is not actionable.
{ "id": "rf_01H...", "draft_id": "dr_01H...", "rule_id": "R1",
  "citation": "GFR 2017, Rule 173 · Manual for Procurement of Goods 2022, para 5.4",
  "severity": "blocking", "target": { "kind": "criterion", "id": "c7" },
  "observed": "annual turnover ≥ ₹40,00,00,000",
  "expected": "≤ ₹24,00,00,000 (2× estimated annual value ₹12,00,00,000)",
  "state": "open",                    // open | resolved | dismissed
  "dismissed_reason": null, "dismissed_by": null }
```

---

## §7 Data model — additions

| ID | Entity | Notes |
|---|---|---|
| E14 | `bid_files` | Every file received, whatever archive it arrived in. Content-hashed for idempotency. |
| E15 | `file_attributions` | Model proposal and human confirmation as **separate** fields. A confirmed value never overwrites the proposal — the audit needs both. |
| E16 | `required_documents` | The register (F17). Frozen at first attribution. Carried verbatim from a draft on publish. |
| E17 | `document_presence` | bid × requirement: verdict, matched file, actor on override. |
| E18 | `spec_requirements` | Technical requirements shredded from the tender. **The denominator.** |
| E19 | `bid_offers` | Extracted offers with anchors. Inventory, not judgement. |
| E20 | `compliance_cells` | requirement × bid: coverage state and both anchors. |
| E21 | `drafts` | The draft tender. Holds category, estimated value, state, rulepack version at publish. |
| E22 | `draft_sections` | Narrative sections with embedded clause snapshots. |
| E23 | `clause_library` | Authority-scoped reusable clauses with provenance. |
| E24 | `rule_findings` | F23 and F24 output. Dismissals carry a reason and an actor. |
| E25 | `draft_reviews` | reviewer × draft: role, comments, sign-off, invalidated-at. |
| E26 | `award_decisions` | Per bidder: outcome, generated-at, actor, and the disclosure field set applied. |

`drafts.state` ∈ `drafting | in_review | published | abandoned`. No hard delete (base §8.3).

**Invariants (enforced, not documented):**
- Every new table carries `authority_id` and an RLS policy. No exceptions, checked at migration review.
- `bid_files.sha256` is unique per `(tender_id, sha256)` — the idempotency guarantee behind F14-AC3.
- Financial content extracted from any file lands in `bid_financials` (E7) and inherits its
  existing lock policy. **No new table may hold a financial figure.**
- `E15.confirmed_bid_id IS NULL AND confidence < ENV-12` defines the triage pile — one definition,
  used by the banner, the count, and the `409 TRIAGE_PENDING` guard.
- `E24` rows with `severity = 'blocking' AND state = 'open'` define the publish block — one query,
  used by the disabled control, the blocker count, and the endpoint guard.
- Every mutation in F15, F17, F18, F23, F25, F26, F27 writes an `audit_events` (E11) row.

---

## §8 Non-functional

### 8.1 Performance

| Operation | Budget |
|---|---|
| Bulk upload of 25 files / 500 pages total → all rows visible with status | p90 ≤ 30s to first render; extraction completes p90 ≤ 15 min with per-file progress |
| OCR of one illegible page | p90 ≤ 6s; pages processed with bounded fan-out (`EVAL_EXTRACT_WORKERS`) |
| Document-presence matrix, 15 bids × 25 requirements | ≤ 1.5s server-side (deterministic; no model in the path) |
| Compliance matrix render, 40 requirements × 5 bids | ≤ 2s server-side |
| Rule checks on a draft | ≤ 500ms — they run on every save, so anything slower changes how the officer writes |

Compute stays co-located with the database. The bidder-side finding stands: a cross-region round
trip costs ~130ms and no amount of code makes it cheaper, only rarer.

### 8.2 The wall

Unchanged and re-asserted, because F20 is the first feature in either product with a strong pull
toward sharing code: the bidder-side compliance matrix solves the same problem. It is copied by
hand, the copy is named in the module docstring, and `tools/check-wall.sh` fails the build on any
import across the boundary. No shared data, no shared credential, no shared data-access module.

### 8.3 Cost

OCR is the only new unbounded cost. Three structural bounds: it runs only on pages already
classified illegible; it is capped per tender by `ENV-9`; exceeding the cap surfaces as
F16-ERR1 with an explicit officer override rather than a silent bill. No new vendor, no new
subscription, no new credential (D7).

---

## §9 Environment inventory — additions

Names only. Values live in `.env` and never leave it.

| ID | Name | Purpose |
|---|---|---|
| ENV-9 | `EVAL_OCR_MAX_PAGES_PER_TENDER` | Vision-OCR page ceiling per tender. Exceeded → F16-ERR1, never silent. |
| ENV-10 | `EVAL_ARCHIVE_MAX_BYTES` | Upload archive size limit |
| ENV-11 | `EVAL_ARCHIVE_MAX_FILES` | Upload archive entry-count limit |
| ENV-12 | `EVAL_ATTRIBUTION_THRESHOLD` | Confidence at or above which a file is auto-attributed (default 0.85) |
| ENV-13 | `EVAL_RULEPACK_PATH` | Versioned GFR/Manual rulepack file. Missing → fail fast (F23-ERR1). |
| ENV-14 | `EVAL_SIGNAL_MIN_TENDERS` | Concluded tenders below which F24 suppresses (default 5) |
| ENV-15 | `EVAL_REQUIRED_SIGNOFF_ROLES` | Comma-separated roles whose sign-off blocks publish |

---

## §10 Fixtures — additions

`pnpm seed:evaluate` remains idempotent and now produces these. Tenant letters match base §10:
**A empty**, **B seeded**, **C isolation probe**.

| ID | Fixture | Tenant | Drives |
|---|---|---|---|
| FIX-9 | ZIP of 24 files, 5 bidders, mixed PDF/XLSX/DOCX; 2 deliberately unattributable; 1 scanned-only | B | F14, F15, **J1-AC6, J1-AC7** |
| FIX-10 | Image-only scanned bid, 30 pages, including one genuinely illegible page | B | F16, F16-ERR2 |
| FIX-11 | Tender with 18 required documents; one bidder missing EMD, one with an ambiguously-named certificate | B | F17, F18 |
| FIX-12 | Tender with 40 technical requirements and 3 bids with known coverage gaps, one contradictory | B | F19, F20, F21 |
| FIX-13 | Authority with **zero drafts** | A | **J3-AC1, J3-AC4**, `/drafts` empty state |
| FIX-14 | Draft with exactly 3 seeded rule violations (turnover > 2× estimate, brand-named spec, short bid window) + 1 missing required sign-off | B | F23, F25, **J3-AC2** |
| FIX-15 | Authority with 6 concluded tenders including one single-bid round and one mass-PQ-failure round | B | F24 |
| FIX-16 | Concluded tender with a final, tie-free ranking and 4 bidders | B | F27, F28, **J1-AC9** |
| FIX-17 | Second authority's draft and clause library, used only to assert they never appear in A or B | C | F22-AC3, isolation suite (CI-blocking) |

---

## §11 Glossary — additions

Base glossary stands. Added:

| Term | Meaning here |
|---|---|
| **Draft** | A tender before publication. Lives in `/drafts`. Becomes a **Tender** at F26 and is read-only thereafter. |
| **Register** | The list of documents a bidder must submit (E16). Authored in a draft or derived from a tender's criteria. Not a checklist *result*. |
| **Presence** | Whether a required document was received. Never "whether it is adequate" (D12). |
| **Attribution** | The binding of an uploaded file to a bidder, document type and envelope. Proposed by model, confirmed by human. |
| **Triage** | The pile of files the engine would not attribute. Non-empty triage blocks screening and presence. |
| **Coverage** | How far a bid's offers address a technical requirement. Evidence, never a verdict. |
| **Finding** | A rule (F23) or historical (F24) observation against a draft. `blocking` stops publication; `advisory` is dismissible with a reason. |
| **Rulepack** | The versioned file encoding the D2 corpus. Stamped onto a tender at publication. |
| **Sign-off** | A named reviewer's approval of a draft. Invalidated by later substantive edits. |
| **Disclosure set** | The exact fields F28 permits for one recipient. Computed before generation, never after. |
| **Reviewer (P5)** | Legal, finance, technical or procurement-cell approver of a draft. Distinct from a TEC member. |

---

## §12 Assumptions register

| # | Assumption | Confidence | Veto cost if wrong |
|---|---|---|---|
| 1 | The J3 authoring journey is correct as drafted — nine steps, publish blocked by findings and sign-offs, ending by creating the tender | **medium** | Medium. It is the largest new surface and journey shape is product taste, not inference. **Veto this first.** |
| 2 | An `ENV-12` attribution threshold of 0.85 puts ≤20% of files in triage on real portal downloads | medium | Low — it is a tunable env var, but the wrong value makes officers distrust the whole intake |
| 3 | Officers will accept a hard publish block on blocking findings rather than demanding an override | medium | Medium — an override path means designing an audited waiver, as the bidder side needed |
| 4 | The ten starter rules (R1–R10) are the right first set, and the citations resolve to the current GFR/Manual text | **low** | Medium. A wrong citation on a blocking rule is worse than no rule. **Needs a procurement-legal read before N4 ships.** |
| 5 | Presence checking is genuinely deterministic once attribution is settled — no adequacy judgement leaks in | high | Low |
| 6 | Vision-model OCR reaches usable accuracy on stamped, rotated and bilingual Indian tender scans | medium | Medium — falling back to a paid OCR vendor is D7 reopened, and it is the only decision here with new spend attached |
| 7 | Reviewers (P5) can be modelled as a role on the existing membership table rather than a new identity type | high | Low |

### Open `TODO:` for a human

- **TODO:** A procurement-legal reviewer must confirm R1–R10's citations and severities against the
  current GFR 2017 and 2022 Manual text before F23 ships. Rules are data (`ENV-13`), so this is a
  file edit, not a code change — but a blocking rule citing the wrong paragraph is worse than
  shipping nine rules instead of ten.
- **TODO:** Confirm whether an audited override on a blocking finding is required (assumption 3).
  If yes, it is modelled on the bidder-side logged-override pattern: secondary-styled control,
  mandatory written reason, permanent audit row.
