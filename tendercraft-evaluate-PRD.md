# TenderCraft Evaluate — Product Requirements

**Buyer-side tender evaluation for Indian public authorities.** The counterpart to TenderCraft
(bidder-side), built as a physically separate product behind a conflict-of-interest wall.

| | |
|---|---|
| Status | Draft v1 · 2026-07-26 |
| Product type | Web app (browser-facing) · multi-tenant · regulated · public money |
| Stage | Greenfield product, brownfield codebase (forks proven infrastructure from TenderCraft) |
| Sibling product | `tendercraft-PRD.md` — bidder-side. **Shares source patterns. Shares zero data.** |

---

## Section 0 — Agent execution contract

Read this before writing code.

1. **Work one milestone at a time** (§5). Never pull work from a later milestone.
2. **Markers.** `TODO:` → stop and ask the human. `ASSUMPTION` → proceed, restate in your summary.
3. **The deterministic rule is inherited and non-negotiable.** AI reads, extracts, locates evidence
   and drafts prose. **Code decides.** Anything that determines responsiveness, qualification,
   a locked mark, a rank, or whether an envelope may open is a pure function in
   `app/deterministic/` with 100% branch coverage. Model output crossing that line is a defect,
   not a shortcut.
4. **Sealed-bid integrity is a code gate, never a UI convention.** If you can reach financial data
   before technical scores are locked by any path — API, direct query, export, error branch —
   that is a Sev-1, equivalent to a tenant-isolation breach.
5. **The COI wall (F13) is architecture, not policy.** No import, no network call, no shared
   credential, no shared model context may connect this product to bidder-side data. A test
   asserts it. See §8.2.
6. **Never build §3 non-goals.**
7. **Every score is attributable to a named human.** There is no system-authored mark anywhere in
   the audit trail.

---

## §1 Product

### 1.1 One sentence

TenderCraft Evaluate turns a pile of submitted bids into a defensible, audit-ready evaluation
report — enforcing the statutory two-bid sequence in code so the process cannot be done out of
order, and so every mark traces to a named evaluator and a cited page.

### 1.2 The problem

A ₹5 Cr government IT tender attracts 8–15 bids of 100–200 pages each. A Technical Evaluation
Committee of 3–5 officers — who have day jobs — must, within a statutory window:

- confirm each bid is responsive against criteria **published in the RFP and unchangeable after**
- score each technically, consistently, against a published rubric
- open financial bids **only** for technically qualified bidders
- produce a recommendation that survives CVC/CAG scrutiny and a losing bidder's challenge

Today this is spreadsheets, email and a shared drive. The failure modes are well known: criteria
drift between bidders, marks with no recorded rationale, a financial envelope opened too early,
and an evaluation report assembled from memory weeks later. Each is a ground for the award to be
challenged and set aside.

### 1.3 Users

| Persona | Role | Primary need |
|---|---|---|
| **P1 Procurement Officer** | Owns the tender; convenes the TEC; publishes the outcome | Get to a defensible recommendation inside the window |
| **P2 TEC Member** | Domain expert; scores the technical envelope | Score fairly and fast without reading 200 pages blind |
| **P3 Committee Chair** | Signs the evaluation report | See where members disagreed before signing |
| **P4 Vigilance / Audit Officer** | Reviews after the fact | Reconstruct exactly who decided what, when, and why |

### 1.4 Success signals

- **Quantitative:** median technical-evaluation elapsed time for a 10-bid tender falls from
  ~15 working days to ≤4. Zero out-of-sequence financial openings (must be structurally 0).
- **Qualitative:** an authority's vigilance officer can answer "why did bidder C lose?" from the
  exported audit pack alone, without asking the TEC.

---

## §2 Journey spine

### 2.1 Trigger

The bid submission deadline has passed. The officer has downloaded the received bids from
GeM/CPPP/state portal (or received them by email/physical cover) and the evaluation clock —
often 30 days — has started.

### 2.2 J1 — Primary journey: RFP to recommendation

The order is statutory, not a design preference. Steps 4→7→8 are separated by a hard gate.

| Step | What the user does | Feature | Entry point | Lands on success |
|---|---|---|---|---|
| J1.1 | Create the evaluation; upload the RFP that was published | F2 | `/evaluations` → "New evaluation" | `/evaluations/:id/framework` |
| J1.2 | Confirm the extracted PQ rules, technical rubric, weights, QCBS ratio; **lock the framework** | F3 | Auto-advance from J1.1 | `/evaluations/:id/committee` |
| J1.3 | Add TEC members; each records a COI declaration | F4 | Framework lock CTA | `/evaluations/:id/bids` |
| J1.4 | Upload the received technical bids | F5 | Committee page CTA | `/evaluations/:id/bids` (per-bid extraction status) |
| J1.5 | Review deterministic PQ screening; mark responsive / non-responsive with reason | F6 | Auto-advance once extraction completes | `/evaluations/:id/screening` |
| J1.6 | **Each member independently** scores each responsive bid, criterion by criterion | F7 | Per-member "Score bids" from `/evaluations/:id` | `/evaluations/:id/score/:bidId` |
| J1.7 | Chair reviews aggregate + variance; **locks technical scores** | F8 | `/evaluations/:id/technical` | `/evaluations/:id/financial` (now reachable) |
| J1.8 | Open financial envelopes — **qualified bidders only** | F9 | Unlocked by J1.7 | `/evaluations/:id/financial` |
| J1.9 | Review combined QCBS ranking and the recommendation | F10 | Auto-advance from J1.8 | `/evaluations/:id/result` |
| J1.10 | Generate and export the evaluation report + audit pack | F11, F12 | Result page primary CTA | Download; evaluation marked Concluded |

**Activation moment — J1.5.** The screening table is the first screen showing every bid side by
side against the published criteria with mandatory failures already flagged and cited to a page.
That is the moment two weeks of work visibly collapses. Everything before it is setup; instrument
J1.5 reached as the activation metric.

### 2.3 J2 — TEC member journey (P2)

A member is not the officer and must not see the whole apparatus.

| Step | Action | Feature | Entry |
|---|---|---|---|
| J2.1 | Accept invitation, sign in | F1 | Emailed link |
| J2.2 | Record COI declaration — **blocks scoring until complete** | F4 | Forced interstitial on first sign-in |
| J2.3 | See only bids assigned to them, only for evaluations they sit on | F7 | `/my-scoring` |
| J2.4 | Score one bid: enter own mark → reveal AI proposal → reconcile → submit | F7 | `/evaluations/:id/score/:bidId` |
| J2.5 | Submitted scores become read-only to that member | F7 | — |

### 2.4 First-run experience

A brand-new authority workspace with zero evaluations lands on `/evaluations`.

- Renders `[data-empty-state]`: "Start your first evaluation", a single primary CTA to
  `/evaluations/new`, and a three-step explainer (Upload the RFP → Add your committee →
  Upload bids).
- **The empty state never renders a bare table.** No dead end.
- A TEC member with no assignments sees "No bids assigned to you yet" plus who to contact —
  never a blank page.

### 2.5 Navigation map

| Route | Screen | Who | Notes |
|---|---|---|---|
| `/login` | Sign in | all | Separate identity pool from bidder product |
| `/evaluations` | Evaluation list | P1, P3 | Home for officers |
| `/evaluations/new` | Create + RFP upload | P1 | |
| `/evaluations/:id` | Evaluation hub — stage meter + blockers | P1, P3 | Mirrors the bidder-side readiness hub pattern |
| `/evaluations/:id/framework` | Criteria, rubric, weights, lock | P1 | Read-only after lock |
| `/evaluations/:id/committee` | TEC members + COI status | P1, P3 | |
| `/evaluations/:id/bids` | Bid intake + extraction status | P1 | |
| `/evaluations/:id/screening` | PQ / responsiveness matrix | P1, P3 | **Activation surface** |
| `/evaluations/:id/score/:bidId` | Scoring workspace | P2 | One bid, one member |
| `/my-scoring` | Member's assigned queue | P2 | Member home |
| `/evaluations/:id/technical` | Aggregate, variance, technical lock | P3 | Lock is here |
| `/evaluations/:id/financial` | Financial opening + rates | P1 | **Unreachable before lock** |
| `/evaluations/:id/result` | QCBS ranking + recommendation | P1, P3 | |
| `/evaluations/:id/audit` | Audit trail + export | P1, P4 | |
| `/settings` | Authority, members, roles | P1 | |
| `/error` | Degraded / 404 | all | |

### 2.6 Screen state coverage

Every screen implements default + loading (skeletons, never a bare spinner) + empty + error.
A blank region on a reachable state is a review failure. Financial routes additionally implement
a **locked** state — an explicit "sealed until technical scores are locked" panel naming what
remains, never a 404 and never a redirect that looks like an error.

### 2.7 Journey acceptance criteria

Run against a **fresh, empty authority account**. No direct URL entry, no prior knowledge.

- **J1-AC1:** A new officer signs in to an empty workspace, and reaches a locked evaluation
  framework using only on-screen affordances. *Verify: browser-verify.*
- **J1-AC2:** From a locked framework, the officer reaches the screening matrix with ≥2 bids
  extracted, using only on-screen affordances. *Verify: browser-verify.*
- **J1-AC3 (the gate):** Before technical lock, `/evaluations/:id/financial` renders the locked
  state, no financial figure appears anywhere in the DOM or in any network response, and
  `GET /api/evaluations/:id/financial` returns `409 FINANCIAL_SEALED`. *Verify: browser-verify + integration.*
- **J1-AC4 (abandon/resume):** An officer who closes the browser mid-scoring returns to
  `/evaluations/:id` and the stage meter names the current step and the exact remaining blockers.
  *Verify: browser-verify.*
- **J1-AC5 (failure recovery):** With the extraction service failing, bid upload surfaces a named
  error and a retry affordance; already-extracted bids stay readable; no bid is silently dropped.
  *Verify: browser-verify.*
- **J2-AC1:** A TEC member who has not filed a COI declaration cannot reach any scoring surface;
  the interstitial states why and what to do. *Verify: browser-verify.*
- **J2-AC2:** A member sees only their assigned bids; requesting another member's scoring URL
  returns 403. *Verify: integration.*

### 2.8 Traceability — zero orphans

| Feature | Journey steps | Entry point | Priority |
|---|---|---|---|
| F1 Authority identity | J2.1, all | `/login` | P0 |
| F2 RFP ingest & criteria extraction | J1.1 | `/evaluations/new` | P0 |
| F3 Framework lock | J1.2 | auto-advance | P0 |
| F4 TEC + COI | J1.3, J2.2 | framework CTA / interstitial | P0 |
| F5 Bid intake & extraction | J1.4 | committee CTA | P0 |
| F6 PQ screening | J1.5 | auto-advance | P0 |
| F7 Independent scoring | J1.6, J2.3–J2.5 | `/my-scoring` | P0 |
| F8 Aggregation + technical lock | J1.7 | `/evaluations/:id/technical` | P0 |
| F9 Financial opening gate | J1.8 | unlocked by F8 | P0 |
| F10 QCBS ranking | J1.9 | auto-advance | P0 |
| F11 Evaluation report | J1.10 | result CTA | P0 |
| F12 Audit trail + export | J1.10 | `/evaluations/:id/audit` | P0 |
| F13 COI wall | — (invariant) | n/a — enforced, not navigated | P0 |

F13 is deliberately the only feature with no journey step: it is a structural invariant, verified
by test rather than reached by a user. Every other feature has an entry point.

---

## §3 Non-goals — never build these

| Non-goal | Why |
|---|---|
| **Portal write-back / auto-award** | Same rule as bidder-side (G-1). Award is a human act on the authority's own system of record. |
| **AI-decided qualification, responsiveness or rank** | Legally indefensible on public money. Code decides; humans mark. |
| **Reading any bidder-side TenderCraft data** | The COI wall (F13). Not a feature to be added later. |
| **Bidder-facing outcome/regret letters** | Outbound legal communication; separate review. Deferred. |
| **L1 / QBS / least-cost methods** | v1 is two-bid QCBS only (§4). |
| **Reverse auction / negotiation support** | Different statutory process entirely. |
| **e-signature / DSC integration** | Authorities have existing DSC infrastructure; integrating is a PH2 question. |
| **Bid receipt or a submission portal** | We evaluate what the authority already received. Becoming a submission portal makes us the system of record and a far larger compliance surface. |

---

## §4 Stack & decisions

| Decision | Status | Value |
|---|---|---|
| Web | **LOCKED** | Next.js 15 App Router + TypeScript + Tailwind (tokens) — forked patterns from bidder-side |
| Engine | **LOCKED** | Python 3.12 + FastAPI, uv |
| **Tenancy isolation** | **LOCKED** | **A separate Supabase project.** Own database, own auth, own storage. Shares source code only. |
| Bid intake | **LOCKED** | Portal-agnostic upload (PDF from any source). No dependency on bidders using TenderCraft. |
| COI wall | **LOCKED** | No shared data, no shared inference, no shared retrieval index. Enforced in code (F13), asserted by test. |
| Evaluation method | **LOCKED** | Two-bid QCBS only in v1 |
| AI role in scoring | **LOCKED** | AI **proposes** a mark; a named human confirms. Proposal is revealed **after** the evaluator records their own mark (F7). |
| Repo layout | PROPOSED | Same monorepo, `apps/evaluate` + `services/evaluate-engine`. Shared design tokens; **no shared data-access module** — sharing `db.py` is how the wall gets breached by accident. |
| LLM | PROPOSED | Same provider as bidder-side, **separate API key and separate project**, so usage/telemetry never commingles |
| Deploy | PROPOSED | Cloud Run, co-located with its own Supabase project (bidder-side learning: co-locate compute and data or pay ~130ms per query) |
| Response envelope | **LOCKED** | `{ ok, data, error: { code, message } }` — inherited |
| Auth | PROPOSED | Supabase Auth on the evaluate project; email invitation only, no public sign-up (authorities are onboarded) |

---

## §5 Build sequence

Vertical slices. Each milestone makes a journey segment walkable.

| M | Scope | Exit criteria |
|---|---|---|
| **M0** | Walking skeleton: separate Supabase project provisioned, schema v0, auth, `/evaluations` empty state, engine `/health`, seed + fixtures, `/verify` proven | Empty state renders; FIX-1 can sign in; **F13-AC1 passes (wall test exists and is green from day one)** |
| **M1** | J1.1–J1.2: RFP upload → criteria extraction → framework review → lock | F2-AC1..3, F3-AC1..3, **J1-AC1** |
| **M2** | J1.3–J1.5: committee + COI, bid intake, extraction, deterministic PQ screening | F4-AC1..3, F5-AC1..3, F6-AC1..4, **J1-AC2**, **J2-AC1** |
| **M3** | J1.6–J1.7: independent scoring with blind-first AI proposal, aggregation, variance, technical lock | F7-AC1..6, F8-AC1..4, **J2-AC2** |
| **M4** | J1.8–J1.9: financial gate, opening, QCBS combination, ranking | F9-AC1..4, F10-AC1..3, **J1-AC3 (the sealed-bid gate)** |
| **M5** | J1.10: evaluation report generation + audit export | F11-AC1..4, F12-AC1..3 |
| **M6** | Hardening: J1-AC4/AC5 recovery paths, all screen states, isolation suite in CI | All P0 ACs green |

M0 ships the COI wall test before any feature. A wall retrofitted after the data model exists is
a wall with holes.

---

## §6 Features

### F1 — Authority identity & roles · P0 · complexity: high
*High: auth boundary + a separate identity pool that must never resolve against bidder-side.*

**Journey:** J2.1; precedes everything. Entry `/login`. Success → `/evaluations` (officer) or
`/my-scoring` (member).

Roles: `officer` (owns evaluations), `member` (scores only), `chair` (locks technical, signs
report), `auditor` (read-only, incl. audit trail). Invitation-only.

- **F1-AC1:** A user account from the bidder-side product cannot authenticate here — separate
  project, separate JWKS. *Verify: integration.*
- **F1-AC2:** A `member` requesting `/evaluations/:id/financial` receives 403 and no financial
  value appears in the response body. *Verify: integration.*
- **F1-AC3:** An `auditor` can read `/evaluations/:id/audit` and cannot mutate anything —
  every write endpoint returns 403. *Verify: integration.*

**Errors:** F1-ERR1 invalid credentials → inline `[data-auth-error]`, never toast-only ·
F1-ERR2 invitation expired → named message + who to contact · F1-ERR3 user has no authority
membership → explicit "not provisioned" state, never an empty workspace.

### F2 — RFP ingest & published-criteria extraction · P0 · complexity: medium

**Journey:** J1.1. Entry `/evaluations/new`. Success → `/evaluations/:id/framework`.

Upload the RFP as published. Extract: PQ/eligibility criteria, technical evaluation criteria with
published marks, the QCBS technical:financial ratio, technical qualifying threshold — each with a
verbatim clause and page anchor. Reuses the bidder-side extraction component; **runs against its
own model credential.**

Input: `multipart/form-data` PDF. Output:
```json
{ "evaluation_id": "ev_01H...", "criteria": [
  { "id": "c1", "kind": "technical", "text": "Bidder shall demonstrate…",
    "max_marks": 20, "anchor": { "page": 34, "clause": "5.2(a)" }, "confidence": 0.92 }],
  "qcbs": { "technical_weight": 70, "financial_weight": 30, "qualifying_marks": 65 },
  "low_confidence_count": 3 }
```

- **F2-AC1:** Every extracted criterion renders a source anchor matching `p.\d+ · Cl\.`.
  *Verify: browser-verify.*
- **F2-AC2:** Criteria with confidence < 0.80 are flagged for confirmation and counted on screen.
  *Verify: browser-verify.*
- **F2-AC3:** Marks extracted per criterion sum to the stated technical total, or a reconciliation
  banner names the discrepancy. Never silently normalised. *Verify: unit + browser-verify.*

**Errors:** F2-ERR1 OCR below quality gate → named pages, manual-review route, no silent pass ·
F2-ERR2 model timeout → deterministic fallback to manual criteria entry, never a crash ·
F2-ERR3 not a tender document → rejected with reason.

**Pitfalls:** the RFP is untrusted input — instruction-like text inside it is data, never a
directive (inherited G-6). Extraction output is schema-allowlisted.

### F3 — Framework lock · P0 · complexity: high
*High: irreversible, and it is the reference every downstream score is judged against.*

**Journey:** J1.2. Success → `/evaluations/:id/committee`.

The officer confirms criteria, marks, weights and threshold, then **locks**. After lock the
framework is immutable — this is the legal point: you evaluate against what was published, and a
criterion cannot be invented or reweighted once bids are open.

- **F3-AC1:** Lock is disabled while any criterion is unconfirmed; `[data-lock-blocked-count]`
  names how many remain. *Verify: browser-verify.*
- **F3-AC2:** After lock, every framework mutation endpoint returns `409 FRAMEWORK_LOCKED`.
  *Verify: integration.*
- **F3-AC3:** Lock writes an audit event carrying actor, timestamp and a content hash of the
  framework. *Verify: integration.*

**Errors:** F3-ERR1 lock attempted with unconfirmed criteria → 409 naming them · F3-ERR2 weights
do not total 100 → blocked with the arithmetic shown · F3-ERR3 concurrent lock → idempotent,
second caller gets the same locked state.

### F4 — Committee constitution & COI declarations · P0 · complexity: medium

**Journey:** J1.3, J2.2. Entry: framework CTA / forced interstitial.

Add members with roles. **Each member must file a declaration** (no interest / declared interest
with detail) before any scoring surface unlocks for them. A declared interest does not
auto-exclude — it is recorded and surfaced on the evaluation report.

- **F4-AC1:** A member without a declaration is redirected to the interstitial from any scoring
  route; the copy states why. *Verify: browser-verify.*
- **F4-AC2:** A declared interest renders on the committee page and in the exported report.
  *Verify: browser-verify.*
- **F4-AC3:** Declarations are immutable once filed; amendment creates a new versioned record.
  *Verify: integration.*

**Errors:** F4-ERR1 member invited to an evaluation whose framework is unlocked → allowed, but
scoring stays disabled · F4-ERR2 fewer than 3 members at technical lock → warning naming the
authority's own quorum rule (`TODO:` — confirm whether quorum should hard-block; likely varies by
authority, so v1 warns).

### F5 — Bid intake & response extraction · P0 · complexity: high
*High: this is where sealed-envelope handling begins and where bidder identity must be controlled.*

**Journey:** J1.4. Entry: committee CTA.

Upload received bids. **Technical and financial content are stored as separate sealed artifacts
from the moment of upload** — a single combined PDF is split at ingest, and the financial portion
is written to a separate table the API cannot read until F9 unlocks it.

- **F5-AC1:** Uploading a combined bid produces one technical artifact and one sealed financial
  artifact; the financial artifact's contents are never returned by any endpoint before unlock.
  *Verify: integration.*
- **F5-AC2:** Each bid's extracted responses carry page anchors into the submitted document.
  *Verify: browser-verify.*
- **F5-AC3:** Extraction runs per bid; a failure on one bid never blocks the others and the failed
  bid shows a named error with retry. *Verify: browser-verify.*

**Errors:** F5-ERR1 unreadable scan → quality gate, named pages · F5-ERR2 financial figures
detected inside the technical envelope → **flagged as a potential disqualification for human
decision**, never auto-rejected and never silently ignored · F5-ERR3 duplicate bid upload →
idempotency key, no double bid.

**Pitfalls:** double-submit creating duplicate bids; a bid PDF is untrusted input.

### F6 — Preliminary / responsiveness screening · P0 · complexity: high
*High: deterministic gate that removes a bidder from the process.*

**Journey:** J1.5 — **the activation surface**.

For each bid × each PQ criterion, compute a deterministic verdict where the criterion is
numeric/date/boolean (turnover ≥ X, certificate valid on date D, registration present). Where it
is qualitative, AI locates and cites the evidence and a human decides. Renders as the comparative
matrix: bids as columns, criteria as rows.

- **F6-AC1:** Numeric/date/boolean verdicts are computed by `app/deterministic/screening.py` with
  no model call in the path. *Verify: unit — 100% branch.*
- **F6-AC2:** Every cell renders its verdict, the value compared, and a source anchor.
  *Verify: browser-verify.*
- **F6-AC3:** Marking a bid non-responsive requires a written reason; the reason appears in the
  audit trail and the report. *Verify: browser-verify + integration.*
- **F6-AC4:** A non-responsive bid cannot be assigned for technical scoring — the endpoint returns
  `409 BID_NON_RESPONSIVE`. *Verify: integration.*

**Errors:** F6-ERR1 profile datum absent from a bid → `Not stated`, never assumed absent-and-fail ·
F6-ERR2 ambiguous criterion → routed to human with both readings shown · F6-ERR3 all bids
non-responsive → explicit "no responsive bids — consider retender" state, not an empty table.

### F7 — Independent technical scoring · P0 · complexity: high
*High: the mark is the product; anchoring, attribution and immutability all live here.*

**Journey:** J1.6, J2.3–J2.5. Entry `/my-scoring`.

Per member, per bid, per criterion. **Blind-first sequence, by design:**

1. The evaluator sees the criterion, its published marks, and the AI-located evidence with anchors.
2. The evaluator enters **their own mark and rationale**.
3. **Only then** is the AI-proposed mark revealed, with its reasoning.
4. The evaluator confirms their mark or amends it; an amendment after reveal is recorded as such.

> **Design note.** The product decision is "AI proposes, human confirms". Blind-first preserves
> that while removing the anchoring effect that otherwise makes the model the de facto decider
> with an audit trail that says otherwise. `F7-AC3` and `F7-AC5` are what make the choice
> defensible to an auditor. Reveal-first is a one-flag change if the authority prefers it —
> `ASSUMPTION (high confidence)` that blind-first is the right default.

- **F7-AC1:** A member sees only bids assigned to them; another member's scoring URL returns 403.
  *Verify: integration.*
- **F7-AC2:** A mark cannot be submitted without a rationale of ≥1 non-whitespace character.
  *Verify: browser-verify.*
- **F7-AC3 (anchoring control):** The AI-proposed mark is absent from the DOM **and from every
  network response** until the evaluator's own mark is recorded. *Verify: browser-verify + integration.*
- **F7-AC4:** A submitted score is read-only to its author; changing it requires an
  officer-initiated reopen that is audited. *Verify: integration.*
- **F7-AC5 (deference metric):** Every score records whether the evaluator's pre-reveal mark
  equalled the AI proposal; per-evaluator deference rate is computed and appears in the audit
  pack. *Verify: unit + integration.*
- **F7-AC6:** Marks outside `0..max_marks` for the criterion are rejected. *Verify: unit.*

**Errors:** F7-ERR1 model unavailable → scoring continues **unimpeded** with no proposal shown;
the absence is recorded · F7-ERR2 session lost mid-scoring → draft marks persist per criterion ·
F7-ERR3 member removed from committee mid-scoring → their submitted scores remain, attributed,
and are excluded from aggregation with the exclusion recorded.

**AI behavior:** model per §4; prompt in `prompts/score_proposal.md`; output schema
`{ proposed_marks: number, reasoning: string, evidence: [{page, clause}] }`; retry cap 1, explicit
timeout; **fallback = no proposal**, never a guess. Eval: golden set of scored bids asserting
schema validity, anchor resolvability and that proposals stay within `0..max_marks` — never
asserting a specific mark.

### F8 — Aggregation, variance & technical lock · P0 · complexity: high
*High: irreversible, and it is the gate that governs F9.*

**Journey:** J1.7. Entry `/evaluations/:id/technical`.

Aggregate member marks per criterion per bid (mean by default). Flag criteria where member
spread exceeds a threshold — divergence is a discussion trigger, not an error. The chair locks.

- **F8-AC1:** Lock is disabled until every assigned (member × responsive bid) pair is submitted;
  the count of outstanding pairs is on screen. *Verify: browser-verify.*
- **F8-AC2:** Criteria with spread ≥ threshold render `[data-variance-flag]` with each member's
  mark shown. *Verify: browser-verify.*
- **F8-AC3:** Technical qualification (aggregate ≥ qualifying marks, from the **locked**
  framework) is computed deterministically. *Verify: unit — 100% branch.*
- **F8-AC4:** Lock writes an audit event with actor, timestamp, and a hash of all constituent
  marks. *Verify: integration.*

**Errors:** F8-ERR1 lock with outstanding scores → 409 naming them · F8-ERR2 zero bids qualify →
explicit state and a recorded recommendation to retender · F8-ERR3 reopen after lock → permitted
to `officer` only, requires a reason, fully audited, and **re-seals the financial envelope**.

### F9 — Financial envelope opening · P0 · complexity: high
*High: **this is the sealed-bid gate.** Breaching it invalidates the tender.*

**Journey:** J1.8. Reachable only after F8 lock.

- **F9-AC1 (the gate):** Before technical lock, `GET /api/evaluations/:id/financial` returns
  `409 FINANCIAL_SEALED` and no financial figure exists in any response payload.
  *Verify: integration.*
- **F9-AC2:** Before lock, `/evaluations/:id/financial` renders the locked state naming what
  remains; no financial value appears in the DOM or the RSC payload. *Verify: browser-verify.*
- **F9-AC3:** Only technically qualified bidders' financial envelopes can be opened; a
  disqualified bidder's financials return 409 permanently. *Verify: integration.*
- **F9-AC4:** Opening writes an audit event per envelope with actor and timestamp.
  *Verify: integration.*

**Errors:** F9-ERR1 open attempted pre-lock → 409, audited as an attempted out-of-sequence access ·
F9-ERR2 financial figure unextractable → manual entry with dual confirmation, never a guess ·
F9-ERR3 technical reopened after financial opening → financials re-seal; the prior opening stays
in the audit trail permanently.

### F10 — QCBS combination & ranking · P0 · complexity: high
*High: money, and it determines who wins.*

**Journey:** J1.9.

Deterministic: normalise financial scores (lowest evaluated price = 100), apply locked weights,
combine, rank. Pure function, no model in the path.

- **F10-AC1:** Combined score = `(technical_score × technical_weight) + (financial_score ×
  financial_weight)` using the **locked** framework weights. *Verify: unit — 100% branch.*
- **F10-AC2:** Every figure on the result screen is traceable to its inputs via an expand
  affordance. *Verify: browser-verify.*
- **F10-AC3:** A tie renders explicitly as a tie with the authority's tie-break rule stated —
  never silently ordered by row order. *Verify: unit + browser-verify.*

**Errors:** F10-ERR1 a qualified bidder with no financial figure → ranking blocked, bidder named ·
F10-ERR2 zero or negative quoted price → flagged for human decision, not auto-ranked.

### F11 — Evaluation report · P0 · complexity: medium

**Journey:** J1.10.

Generates the defensible document: methodology and locked framework, committee and COI
declarations, per-bid responsiveness with reasons, per-criterion marks with rationale and
attribution, variance notes, financial comparison, ranking, recommendation. DOCX/PDF.

- **F11-AC1:** Every mark in the report is attributed to a named evaluator with their rationale.
  *Verify: integration.*
- **F11-AC2:** Report generation is blocked until F10 ranking exists; the button is `disabled`,
  not merely the endpoint. *Verify: browser-verify.*
- **F11-AC3:** Every numeric figure in the report is transcluded from stored data — no figure is
  model-authored. *Verify: unit + integration.*
- **F11-AC4:** COI declarations, including declared interests, appear in the report.
  *Verify: integration.*

**Errors:** F11-ERR1 generation while data mutates → snapshot at generation, version-stamped ·
F11-ERR2 renderer failure → envelope error, zero bytes, never a partial document.

### F12 — Audit trail & export · P0 · complexity: high
*High: append-only integrity; it is the artifact a vigilance officer relies on.*

**Journey:** J1.10; browsable at `/evaluations/:id/audit`.

Append-only record of every consequential act: framework lock, COI filing, responsiveness
decision + reason, each score with pre/post-reveal values, technical lock, each envelope opening,
every reopen and override with reason, report generation, export.

- **F12-AC1:** `audit_events` rejects UPDATE and DELETE at the database level, service role
  included. *Verify: integration.*
- **F12-AC2:** Export produces a file whose recorded content hash matches on re-verification.
  *Verify: integration.*
- **F12-AC3:** Every score row in the export carries actor, timestamp, pre-reveal mark, AI
  proposal (or its absence), final mark and rationale. *Verify: integration.*

**Errors:** F12-ERR1 export of an in-progress evaluation → permitted, watermarked
`INTERIM — evaluation not concluded`.

### F13 — Conflict-of-interest wall · P0 · complexity: high
*High: it is the product's licence to exist in this market.*

No journey step — a structural invariant.

- **F13-AC1:** No module under `apps/evaluate` or `services/evaluate-engine` imports from the
  bidder-side app/engine packages, and no bidder-side connection string, key or host appears in
  its configuration. Enforced by an import/config check in CI. *Verify: integration (CI-blocking).*
- **F13-AC2:** The evaluate engine's Supabase host differs from the bidder-side host; a test
  asserts they are not equal and fails the build if they converge. *Verify: integration.*
- **F13-AC3:** The scoring model receives only content from this project — no retrieval index,
  cache or prompt fixture sourced from bidder-side data. *Verify: integration.*
- **F13-AC4:** The wall is stated in-product on a page an authority can show its own vigilance
  officer. *Verify: browser-verify.*

---

## §6.1 API surface

Every response uses the inherited envelope `{ ok, data, error: { code, message } }`, including
errors. Binary export endpoints return bytes on 2xx and the envelope on every error path.

| Method | Endpoint | Feature | Notable statuses |
|---|---|---|---|
| POST | `/api/evaluations` | F2 | 201 · 422 `NOT_A_TENDER` |
| GET | `/api/evaluations/:id/criteria` | F2 | 200 |
| POST | `/api/evaluations/:id/framework/lock` | F3 | 200 · 409 `FRAMEWORK_UNCONFIRMED` · 409 `WEIGHTS_INVALID` |
| POST | `/api/evaluations/:id/members` | F4 | 201 · 403 `NOT_OFFICER` |
| POST | `/api/evaluations/:id/coi` | F4 | 201 · 409 `COI_ALREADY_FILED` |
| POST | `/api/evaluations/:id/bids` | F5 | 201 · 409 `DUPLICATE_BID` · 422 `OCR_QUALITY_GATE` |
| GET | `/api/evaluations/:id/screening` | F6 | 200 |
| PUT | `/api/evaluations/:id/bids/:bidId/responsiveness` | F6 | 200 · 422 `REASON_REQUIRED` |
| POST | `/api/evaluations/:id/scores` | F7 | 201 · 403 `NOT_ASSIGNED` · 409 `COI_NOT_FILED` · 422 `MARK_OUT_OF_RANGE` |
| GET | `/api/evaluations/:id/scores/:bidId/proposal` | F7 | 200 · **409 `OWN_MARK_REQUIRED`** (blind-first) |
| POST | `/api/evaluations/:id/technical/lock` | F8 | 200 · 409 `SCORING_INCOMPLETE` |
| GET | `/api/evaluations/:id/financial` | F9 | 200 · **409 `FINANCIAL_SEALED`** · 409 `BID_NOT_QUALIFIED` |
| POST | `/api/evaluations/:id/financial/open` | F9 | 200 · 409 `FINANCIAL_SEALED` |
| GET | `/api/evaluations/:id/result` | F10 | 200 · 409 `FINANCIAL_NOT_OPENED` |
| POST | `/api/evaluations/:id/report` | F11 | 200 (bytes) · 409 `RANKING_INCOMPLETE` |
| GET | `/api/evaluations/:id/audit` | F12 | 200 |
| GET | `/api/evaluations/:id/audit/export` | F12 | 200 (bytes) |

Error codes are `SCREAMING_SNAKE` throughout; the web UI switches on `code`, never on message text.

## §6.2 Known pitfalls by feature

Written before the bugs, not after. Every `high`-complexity feature appears here.

| Feature | Pitfall | Guard |
|---|---|---|
| F1 | A bidder-side account resolving here because both products share a JWT issuer | Separate Supabase project ⇒ separate JWKS. `F1-AC1` asserts it. |
| F1 | Role checked in the UI but not the endpoint — a `member` curling a financial URL | Authorization at the handler, derived from the verified JWT, never from a body param |
| F3 | Framework edited after lock through a path that skips the guard (bulk update, admin tool, migration) | Guard in the data layer, not the route; `F3-AC2` covers every mutation endpoint |
| F5 | Splitting a combined PDF wrongly and writing financial pages into the technical artifact | Split verified by content scan; `F5-ERR2` flags detected figures for a human rather than auto-deciding |
| F6 | "Absent from the bid" silently treated as "fails the criterion" — disqualifies a bidder on an extraction miss | `Not stated` is its own verdict requiring human resolution (`F6-ERR1`) |
| F6 | Comparators drifting into prompts, so the model decides responsiveness | `app/deterministic/screening.py`, import check in CI, 100% branch coverage |
| F7 | The AI proposal leaking into the RSC payload or a prefetch even though the UI hides it | `F7-AC3` asserts absence from the **network response**, not just the DOM |
| F7 | Anchoring making the model the de facto decider while the audit trail claims human authorship | Blind-first sequence + deference rate (`F7-AC5`) — the metric an auditor reads |
| F7 | A member's draft marks lost on session expiry, silently re-entered differently | Per-criterion draft persistence (`F7-ERR2`) |
| F8 | Aggregating over members who were removed mid-evaluation | Exclusion is explicit and recorded (`F7-ERR3`) |
| F9 | The gate enforced in the page but not the API, the export, or an error branch that returns partial data | `F9-AC1` is an integration test on the endpoint; the isolation suite probes every path |
| F9 | Technical reopened after financials were seen — the bell cannot be un-rung | Re-seal, and the prior opening stays in the audit trail permanently (`F9-ERR3`) |
| F10 | Floating-point drift making two equal bids rank arbitrarily | Decimal arithmetic; exact ties render as ties (`F10-AC3`) |
| F10 | Financial normalisation dividing by zero on a ₹0 quote | `F10-ERR2` routes it to a human |
| F12 | An UPDATE grant on `audit_events` added by a later migration | Grant revoked at DB level; `F12-AC1` asserts it against the service role |
| F13 | A well-meaning refactor extracting a shared `db.py` across both products | No shared data-access module, by rule; `F13-AC1` is an import check in CI |
| F13 | Convergent config — someone points staging at the bidder database "just to test" | `F13-AC2` fails the build if the hosts are equal |

## §6.3 Core data shapes

```jsonc
// E9 scores — the row an auditor reads. pre_reveal_mark is what makes F7-AC5 computable.
{ "id": "sc_01H...", "authority_id": "au_01H...", "evaluation_id": "ev_01H...",
  "bid_id": "bd_01H...", "criterion_id": "c1", "evaluator_id": "us_01H...",
  "pre_reveal_mark": 14, "ai_proposed_mark": 16, "final_mark": 15,
  "rationale": "Architecture covers HA but omits DR RPO/RTO.",
  "amended_after_reveal": true, "submitted_at": "2026-08-02T09:14:22Z" }

// E7 bid_financials — sealed. No endpoint returns `amount` before F9 unlock.
{ "id": "fi_01H...", "bid_id": "bd_01H...", "sealed": true,
  "amount_inr": null, "opened_at": null, "opened_by": null }

// F10 result row
{ "bid_id": "bd_01H...", "bidder": "Meridian Infotech Pvt Ltd",
  "technical_score": 78.5, "technically_qualified": true,
  "financial_score": 92.3, "combined_score": 82.64, "rank": 2, "tied_with": [] }
```

---

## §7 Data model

| ID | Entity | Notes |
|---|---|---|
| E1 | `authorities` | The tenant. RLS root. |
| E2 | `authority_members` | user × authority × role. Membership grants everything. |
| E3 | `evaluations` | The tender being evaluated. Holds stage + lock timestamps. |
| E4 | `criteria` | Extracted, confirmed, frozen at framework lock. Carries anchors + marks. |
| E5 | `framework_locks` | Append-only: actor, timestamp, content hash. |
| E6 | `bids` | One per bidder. Holds technical artifact ref + bidder identity. |
| E7 | `bid_financials` | **Separate table.** Row-level sealed; readable only after F9 unlock. |
| E8 | `responsiveness_decisions` | Per bid × criterion: verdict, reason, actor. |
| E9 | `scores` | member × bid × criterion: pre-reveal mark, AI proposal, final mark, rationale. |
| E10 | `coi_declarations` | Versioned, immutable. |
| E11 | `audit_events` | Append-only; UPDATE/DELETE revoked at DB level. |

**Invariants (enforced, not documented):** every table carries `authority_id` + an RLS policy ·
`bid_financials` has an additional policy keyed on the evaluation's technical-lock state ·
`scores.final_mark` ∈ `0..criteria.max_marks` as a CHECK constraint · `audit_events` has no
UPDATE/DELETE grant.

---

## §8 Non-functional

### 8.1 Performance
Extraction of a 200-page bid: p90 ≤ 10 min, with per-stage progress shown (never a bare spinner).
Screening matrix for 15 bids × 40 criteria renders ≤ 1.5s server-side. Compute is co-located with
the database — see the bidder-side latency finding.

### 8.2 The wall (restated because it is the highest-stakes requirement)
Different Supabase project, different auth pool, different model credential, no shared data-access
module, no shared retrieval index. `F13-AC1..3` are CI-blocking. A change that makes the two
products share a database is not a refactor — it is the end of the product's viability with a
government buyer.

### 8.3 Compliance posture
- Data residency: **India region required before any real bid data.** Unlike the bidder-side demo,
  this is not deferrable — bid contents are commercially sensitive third-party data held by a
  public authority. `TODO:` confirm the authority's own residency and empanelment requirements
  before first production use.
- Retention: evaluation records retained per the authority's schedule, typically 5–8 years.
  `TODO:` confirm.
- Every model call logged with token/cost attribution per evaluation.

---

## §9 Environment inventory

Names only. Never values.

| ID | Var | Purpose |
|---|---|---|
| ENV-1 | `NEXT_PUBLIC_EVAL_SUPABASE_URL` | Evaluate project URL — **must differ from bidder-side** |
| ENV-2 | `NEXT_PUBLIC_EVAL_SUPABASE_ANON_KEY` | Public by design |
| ENV-3 | `EVAL_SUPABASE_SERVICE_JWT` | Engine only. Never in web. |
| ENV-4 | `EVAL_MODEL_API_KEY` | **Separate credential** so usage never commingles |
| ENV-5 | `EVAL_ENGINE_URL` | Web → engine |
| ENV-6 | `EVAL_DOCUMENTS_BUCKET` | Bid storage |
| ENV-7 | `EVAL_VARIANCE_THRESHOLD` | Marks spread that raises the flag (default 20% of max) |

---

## §10 Fixtures

`pnpm seed:evaluate` resets all fixtures idempotently.

**Two authorities are seeded, deliberately.** Journey ACs must run against a genuinely empty
account — a J-AC executed on a pre-populated workspace tests nothing about first-run — so the
empty tenant is kept clean and every seeded artifact lives in the other one. That separation
doubles as a live tenant-isolation fixture.

| ID | Fixture | Tenant | Drives |
|---|---|---|---|
| FIX-1 | Officer `officer@empty.test`, authority "Greenfield Nagar Palika", **zero evaluations** | A (empty) | All J-ACs, first-run, `[data-empty-state]` |
| FIX-2 | Officer `officer@authority.test`, authority "Test Municipal Corporation" | B (seeded) | Feature-level browser-verify |
| FIX-3 | Three TEC members, one with a declared interest, one with no COI declaration filed | B | F4, F7, J2-AC1, report |
| FIX-4 | Sample RFP (~40pp): 12 PQ + 9 technical criteria, QCBS 70:30, threshold 65, 3 sub-0.80 confidence items | B | F2, F3 |
| FIX-5 | Five submitted bids: 3 responsive, 1 failing a mandatory PQ, 1 with financials leaked into the technical envelope | B | F5, F6, F5-ERR2 |
| FIX-6 | Partially scored evaluation — 2 of 3 members submitted | B | F8 lock blocking, J1-AC4 |
| FIX-7 | Fully scored, technically locked evaluation with sealed financials | B | **J1-AC3 / F9-AC1 — the gate test** |
| FIX-8 | A second authority's evaluation, used only to assert it never appears in tenant A or B responses | C | Isolation suite (CI-blocking) |

---

## §11 Glossary

| Term | Meaning here |
|---|---|
| **Evaluation** | One tender being assessed. The top-level object. Not a "project". |
| **Framework** | The published criteria, marks, weights and threshold. Immutable after lock. |
| **Envelope** | Technical or financial portion of a bid. Sealed until its stage opens. |
| **Responsive** | Bid meets mandatory PQ criteria and may proceed to technical scoring. |
| **TEC** | Technical Evaluation Committee. |
| **QCBS** | Quality and Cost Based Selection — weighted technical + financial. |
| **Qualifying marks** | Technical aggregate below which a bid is disqualified before financial opening. |
| **Lock** | An irreversible, audited state transition. Framework lock and technical lock are distinct. |
| **Deference rate** | Share of a member's marks that matched the AI proposal before reveal. An audit signal, not a performance metric. |
| **Wall** | The COI separation between this product and bidder-side TenderCraft. |

---

## §12 Assumptions register

| # | Assumption | Confidence | Veto cost if wrong |
|---|---|---|---|
| 1 | Blind-first reveal is the right default for AI-proposed marks | high | One flag; low |
| 2 | Mean is the right default aggregation across members | medium | Low — add median/trimmed-mean |
| 3 | Authorities will upload bids rather than expect portal integration | high | High — portal integration is a large surface |
| 4 | A declared interest is recorded, not auto-excluding | medium | Low |
| 5 | Quorum is warned, not hard-blocked (F4-ERR2) | low | Low — flip to a gate |
| 6 | Single authority per workspace; no parent/department hierarchy in v1 | medium | Medium — data model change |

**Open `TODO:` for a human:** committee quorum rule (F4-ERR2) · data residency and empanelment
requirements (§8.3) · retention schedule (§8.3) · the authority's tie-break rule (F10-AC3).
