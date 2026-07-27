# TenderCraft — Discovery, Triage & Traceability (Modules F, G + C/B deltas)

**Version:** 1.0 (Draft for engineering review) · **Date:** 26 July 2026 · **Status:** Confidential
**Audience:** Engineering, Data Science, Design, QA · **Owner:** Product
**Relationship to the base PRD:** this document **extends** [`tendercraft-PRD.md`](tendercraft-PRD.md) (sha-pinned by `docs/DESIGN_SPEC.md` §I — never edited). Every doctrine, guardrail (G-1…G-7), error-tolerance class (ET-1…ET-6), and the AI-vs-deterministic table in base §2.4 apply here unchanged. New IDs continue the base numbering: modules **F**, **G**; tolerances **ET-7…ET-9**; guardrails **G-8…G-10**; edge cases **EC-8…EC-13**; rollbacks **RB-5…RB-8**; screens **S14…S18**.

---

## 1. Why this document exists

Three P0 bidder pain points were submitted. Mapped honestly against what the base PRD already specifies:

| # | Pain point | Already specified? | Real gap this PRD closes |
|---|---|---|---|
| **P0-1** | Fragmented monitoring of hundreds of tender portals; different teams track different portals; daily. Excel trackers, email alerts, ad-hoc RSS. | **No.** Base Appendix A lists discovery aggregators as *competitors*; the base product starts at "user uploads a tender". | **Module F** — acquisition, dedup, watchlists, and a ranked daily opportunity feed. Net-new surface. |
| **P0-2** | Manual eligibility checks against turnover / experience / certifications, every bid. Excel checklists, reading the RFP, asking finance. | **Partly.** Module C already does per-criterion verdicts, gap quantification and Bid/No-Bid — but only for **one tender the user already decided to upload**, after full ingestion. | **Module C delta (C-FR6…C-FR9)** — eligibility as a *triage* function that runs on the whole inbound feed cheaply and automatically, so the check happens before a human reads anything. |
| **P0-3** | Manual requirement-to-response mapping in Excel/Word; RFP shredded by hand; poor reuse. | **Partly.** Module A produces the locked TOM, and screen S10 renders a compliance matrix — but only as an *export gate* at the end of the Generator flow. A bid manager who never uses the Generator gets nothing. | **Module G** — the compliance matrix as a first-class, standalone, Excel-round-trippable artifact available immediately after TOM lock, plus an answer-reuse library and a deterministic unmapped-requirement count. |

**The through-line.** All three pains are the same failure at different depths: *the bidder's attention is spent on mechanical routing rather than on winning.* F routes tenders to the right bidder, C-delta routes effort to the tenders that are winnable, G routes requirements to the people and evidence that answer them.

**What this PRD does not do.** It does not restate Modules A, B, D, E. It does not touch the base guardrails. It adds no portal write path — G-1 stands, and Module F **hardens** it (see §5).

---

## 2. Problem statement

### 2.1 P0-1 — Discovery is a distributed manual crawl

Indian public procurement is published across GeM, CPPP/eProcure, 25+ state e-procurement portals (most running NIC's eProcurement stack), PSU-specific portals, and corporate RFP channels (email, vendor portals). No single authoritative feed exists. Consequences observed in the submitted pain data:

- Monitoring is split by team member and by portal, so **coverage is a function of who was at their desk**. There is no shared, auditable definition of "everything we could have bid on this week".
- Excel trackers are copy-paste snapshots — they go stale the moment a corrigendum moves a deadline, and they carry no link back to the source clause.
- Portal search is keyword-based over titles that are frequently mis-categorised, so **the relevant tender does not surface for the words the bidder would think to use**.
- The cost of a miss is asymmetric and invisible: a high-value tender that was never seen produces no error message, no alert, and no line in any report. It is the only P0 here with **zero natural feedback signal**, which is why §7 makes backtested recall the primary metric rather than a satisfaction score.

**Frequency:** daily. **Who:** bid managers (P2), SME owners doing it themselves (P1), consultants monitoring on behalf of many clients (P3).

### 2.2 P0-2 — Eligibility is checked too late and by hand

Today (and in the base product as specified), an eligibility answer costs a full ingestion: someone decides a tender is worth reading, uploads it, waits for OCR and extraction, verifies low-confidence criteria, locks the TOM, then runs the analysis. That is the right depth for a bid under active consideration and the **wrong** depth for the 200 tenders that arrived this week. The result is that the human triage filter stays manual — reading NIT PDFs, cross-checking turnover with finance, hunting for a certificate's expiry date — which is exactly the labour the base PRD promised to remove, applied at the point where it is most repetitive.

The root cause is not model capability. It is that **the profile side of the comparison is already structured and never changes between tenders.** Turnover, net worth, experience records, certifications and their expiry dates sit in the vendor profile (base Module C schema). An eligibility answer for a new tender needs only the tender side extracted — and the *eligibility* subset of a tender (turnover threshold, experience count and value, mandatory certifications, EMD, MSE clauses) is a small, highly patterned fraction of an NIT that is usually present in the first few pages or in the portal's own structured listing fields.

### 2.3 P0-3 — Requirement→response mapping is rebuilt from scratch each bid

The RFP is shredded by hand into an Excel compliance matrix. Three failures follow:

1. **Silent omission.** A hand-shred has no denominator. Nobody can state how many requirement sentences existed, so "we covered everything" is an assertion, not a measurement. This is base ET-4 (missed mandatory criterion) arriving one step earlier than the base PRD catches it.
2. **No reuse.** The same certifications, the same methodology, the same past-performance narratives are re-typed every bid, because prior answers live inside finished Word documents rather than in an indexed, per-requirement store. The submitted root cause — "poor reuse" — is a data-model problem, not a discipline problem.
3. **Tool split.** The matrix lives in Excel while the evidence lives in a document store, so provenance is lost at the first copy-paste and cannot be reconstructed at review time.

---

## 3. Module F — Opportunity Discovery & Monitoring

**Purpose.** Produce one shared, auditable, deduplicated stream of every tender the workspace could bid on, ranked by a decomposed fit signal, delivered daily — and prove, by backtest, that it does not miss.

### 3.1 Source acquisition (normative — read §5 before implementing)

Sources are tiered by legal posture and reliability. **A source may only be enabled if it appears in the allowlist registry with a recorded acquisition mode.**

| Tier | Source | Mode | Notes |
|---|---|---|---|
| **T1** | Official machine-readable publications (portal-published RSS/exports/open-data releases where they exist) | Poll published endpoint | Preferred wherever available. Availability per portal is **ASSUMPTION — verify at build time**; treat every T1 source as revocable and degrade to T2 or T3 rather than to a workaround. |
| **T2** | Public, unauthenticated listing pages of NIC-stack eProcurement instances and GeM/CPPP public search | Robots-respecting crawl | ~25 state portals share the NIC eProcurement codebase, so **one adapter plus per-instance base URL + parser fingerprint covers most of the long tail**. Adapter count, not portal count, is the engineering unit. |
| **T3** | **Customer-forwarded portal alert emails** — each workspace gets `tenders@<workspace-key>.inbox.<domain>`; the customer forwards or auto-forwards the alert emails the portals (and any paid aggregator they already subscribe to) already send them | Inbound email parse | Zero ToS exposure — it is the customer's own mail, delivered to them by the portal. Covers portals we do not crawl and portals behind login. **Lowest legal risk and lowest build cost of any source; ship it first.** |
| **T4** | Manual URL paste / document upload | User action | Always available; the floor when everything else fails. |

- **F-FR1 Adapter contract.** Every source adapter emits the same normalized record: `{source_id, portal_ref_no, title, authority, category_codes, geography, estimated_value, emd, published_at, closing_at, prebid_at, document_urls[], raw_snapshot_ref}`. Fields the source does not provide are `null` — **never inferred by a model into a field a deterministic filter reads** (see §4).
- **F-FR2 Raw snapshot retention.** Every fetched listing and document is stored verbatim with its retrieval timestamp and source URL. A feed item with no reproducible snapshot cannot render (this is base A-AC3's source-anchor discipline applied to discovery).
- **F-FR3 Freshness.** T3 email items appear in the feed within **15 minutes** of receipt. T1/T2 polled items appear within **6 hours** of portal publication. Polling cadence per source is configurable and rate-limited (§5).
- **F-FR4 Corrigendum watch.** Any tender on a watchlist — whether or not it has been ingested into a TOM — is re-polled until its closing date. Changes to `closing_at`, `estimated_value`, or eligibility-bearing fields raise an alert and, for ingested tenders, feed base A-FR3's corrigendum diff.
- **F-FR5 Source health.** Each adapter reports last-success, parse-error rate, and item-count deviation vs. its trailing median. A source that returns zero items where it historically returned some is **an incident, not an empty feed** — see EC-8.

### 3.2 Deduplication

The same tender legitimately appears on a state portal, on CPPP as a mirror, in two forwarded emails, and in an aggregator digest.

- **F-FR6 Deterministic merge only.** Records merge into one opportunity **only** on an exact normalized `portal_ref_no` match (whitespace, case, and separator normalization; no fuzzy edit distance).
- **F-FR7 Candidate grouping, never hiding.** Near-matches (same authority + closing datetime + high title similarity) render as a **grouped card with a "possible duplicate" affordance**. They are never auto-merged and never suppressed. Rationale: a wrong merge deletes a tender from the user's world with no error message — the exact failure mode P0-1 exists to prevent (ET-7).
- **F-FR8 Provenance preserved.** A merged opportunity lists every source it was seen on, with timestamps. "Which portal was this on?" must be answerable without a support ticket.

### 3.3 Triage and ranking

Ranking is **decomposed and never a single opaque score.** Every feed item carries three independent signals:

- **F-FR9 Gate signal (deterministic).** Runs the workspace's own saved rules over the normalized record: category codes, geography, value band, minimum days-to-close. Produces `in-scope | out-of-scope (rule: <name>)`. Rules are user-authored, named, editable, and every exclusion names the rule that caused it.
- **F-FR10 Eligibility signal (Module C delta — §4).** `Likely eligible | Likely ineligible (reason) | Unknown — needs the NIT`. Never rendered as a bare colour; always carries the criterion that decided it.
- **F-FR11 Relevance signal (AI).** Semantic match of the tender's scope against the workspace's experience records and won-bid history, as a **band** (High / Medium / Low) with the matched past project cited. Bands, not decimals — a decimal implies a precision this signal does not have.
- **F-FR12 No silent discard (hard).** Nothing is deleted. Filtered items move to an **Excluded** bucket that always displays its count ("142 hidden by 3 of your rules"), is one click away, and is fully searchable. **A model may never move an item to Excluded** — only a user-authored deterministic rule may (ET-7, G-9).
- **F-FR13 Daily digest.** One email/notification per workspace per day: new in-scope items, deadline escalations on watched tenders (reusing base E-FR6's T-72/48/24h thresholds), and corrigenda. Per-user delivery preferences; per-workspace shared truth.
- **F-FR14 Assignment.** A feed item can be assigned to a member, moving it from "someone should look at this" to a named owner — the direct fix for "different teams track different portals".
- **F-FR15 Summarisation.** Each item carries a 3-line model-written summary (scope, who is buying, what is unusual) with **every claim anchored to the source listing or NIT page**. Uncited summary sentences are dropped, not shown (base G-5 applied to discovery).

### 3.4 User stories

**F-US1** As a bid manager, I open one feed each morning and see every new tender that matched our rules across all portals, deduplicated, with the ones we are eligible for at the top.
**F-US2** As an SME owner, I never learn about a tender after its deadline again — deadline escalations reach me on the tenders I am watching.
**F-US3** As a consultant, I run separate feeds per client workspace and never see client A's rules or shortlist inside client B (base ET-6).
**F-US4** As a bid manager, I can prove to my partner what we *could* have bid on last quarter and what we chose not to — with the exclusion rule named for every skip.

### 3.5 Acceptance criteria

| ID | Criterion | Threshold | Method |
|---|---|---|---|
| F-AC1 | **Backtested recall** — of the tenders a design partner actually bid on in the prior 12 months, the share the feed surfaces as in-scope when replayed | ≥ 95% | Replay harness against partner-supplied bid history; the primary gate for P0-1 |
| F-AC2 | Precision of the in-scope bucket — items a partner rates "worth a look" | ≥ 60% of daily in-scope volume, and in-scope volume ≤ 25 items/day/workspace at default rules | Weekly partner rating sample |
| F-AC3 | Duplicate rate in the in-scope bucket (same tender shown as two opportunities) | ≤ 2% | Deterministic audit against `portal_ref_no` |
| F-AC4 | Wrong merges (two distinct tenders shown as one) | **0** — hard gate | Deterministic audit + F-FR6 enforcement test |
| F-AC5 | Freshness: T3 email ≤ 15 min, T1/T2 ≤ 6h from portal publication | ≥ 99% of items | Ingestion timestamp telemetry |
| F-AC6 | Items in the Excluded bucket that were excluded by anything other than a named user rule | **0** — hard gate | Deterministic gate + logs |
| F-AC7 | Feed items rendering a resolvable source link and retrieval timestamp | 100% | Deterministic validator |
| F-AC8 | Corrigendum detection on watched tenders (deadline/value/eligibility changes) | ≥ 95% within one poll cycle | Seeded-corrigendum replay set |

---

## 4. Module C delta — eligibility as triage (P0-2)

The base Module C stays exactly as specified for tenders under active consideration. This delta adds a **cheap, early, automatic** pass so the human never performs the check by hand.

- **C-FR6 Two-depth eligibility.** *Depth 1 (triage)* runs automatically on every in-scope feed item using only the normalized listing record plus the **first-pass eligibility extraction** (§4.1). *Depth 2 (full)* is the existing base Module C run over a locked TOM. Depth 1 output is always labelled as provisional and always names its depth in the UI.
- **C-FR7 Eligibility-only extraction.** A narrow extractor targets the eligibility subset only: average annual turnover threshold and its FY window, net worth, similar-work experience (count, individual value, aggregate value, recency window), mandatory certifications, EMD amount and exemption clauses, MSE/DPIIT relaxations, and bidder-type restrictions (OEM-only, MSE-reserved, class-I/II local content). Output is schema-allowlisted; tender text remains untrusted input (base G-6).
- **C-FR8 Same comparators, same doctrine.** Depth 1 verdicts run through the **existing deterministic comparators** in `app/deterministic/` — no separate "quick" logic path. A cheaper input never buys a looser rule. Fuzzy criteria at Depth 1 default to `Unknown`, never `Likely eligible` (base C-FR2, ET-1).
- **C-FR9 Conservative asymmetry, inverted for triage.** Base Module C errs toward Needs-review to protect against ET-1 (telling a bidder they qualify when they do not). At Depth 1 the asymmetry inverts for *display ordering only*: a `Likely ineligible` item is ranked down but **never hidden** (F-FR12), because a Depth-1 false negative on thin data would recreate P0-1's invisible miss. A Depth-1 verdict never gates anything; only Depth 2 feeds a Bid/No-Bid recommendation.
- **C-FR10 Profile-change replay.** When the vendor profile changes materially (a certification renews, a new FY turnover lands, a project completes), Depth 1 re-runs across open opportunities and surfaces newly-eligible tenders. The submitted process — "asking finance" — happens once into the profile, not once per tender.
- **C-FR11 Gap rollup.** A workspace-level view answers "what single missing credential is costing us the most open tenders?" — count and aggregate value of open opportunities blocked by each individual missing/expired item. This turns base Module C's per-tender gap list into a procurement-capability roadmap.

### 4.1 Cost and escalation policy

Depth 1 must be cheap enough to run on everything. Escalation is deterministic and capped:

1. Listing-record comparators only — **zero model calls** where the portal already publishes turnover/EMD/category fields.
2. If eligibility fields are absent, fetch the NIT and run the eligibility-only extractor over its **first N pages plus any page whose text matches the eligibility-section heading patterns** — not the whole document.
3. Full ingestion (base Module A) runs **only** on user action (shortlist / watch / "analyse"), or automatically for items above a workspace-configured value threshold, capped per day. Cost per workspace-day is logged and rendered in settings.

### 4.2 Acceptance criteria

| ID | Criterion | Threshold | Method |
|---|---|---|---|
| C-AC6 | Depth-1 `Likely ineligible` items that Depth 2 later confirms ineligible | ≥ 90% | Depth-1 vs Depth-2 agreement set |
| C-AC7 | Depth-1 items marked `Likely eligible` that Depth 2 finds hard-ineligible on a mandatory gate | ≤ 10%, and **0** where the deciding field was present in the listing record | Agreement set + deterministic audit |
| C-AC8 | Fuzzy criteria auto-passed at Depth 1 | **0** — hard gate | Deterministic gate + logs |
| C-AC9 | Depth-1 verdicts rendering the deciding criterion and its source | 100% | Deterministic validator |
| C-AC10 | Every Depth-1 verdict visibly labelled provisional and never feeding a Bid/No-Bid card | 100% | DOM + deterministic gate |
| C-AC11 | Profile-change replay surfaces newly-eligible open opportunities within one cycle | ≥ 95% | Seeded profile-mutation set |

---

## 5. Portal integrity, legality, and rate discipline (normative)

Base §9 states: read/assist only, no credentialed scraping in violation of portal terms, no automated submission. Module F is the module most able to violate that, so it carries explicit guardrails.

- **G-8 No authenticated acquisition.** Adapters never log in, never replay a session cookie, never store portal credentials, and never solve or bypass a CAPTCHA or bot check. A source that requires authentication is served by T3 (customer's own forwarded email) or not at all. Attempts are refused and logged (mirrors base G-7).
- **G-9 No model-driven exclusion.** Only a named, user-authored deterministic rule may move an item out of the primary feed (F-FR12). Model output may rank and summarise; it may not decide what a human never sees.
- **G-10 Crawl discipline.** Every T2 fetch: honours `robots.txt`, identifies itself with a stable user agent carrying a contact URL, applies a per-host concurrency and rate cap, backs off exponentially on 429/5xx, caches aggressively, and never re-fetches an unchanged page within its TTL. A source's registry entry records its terms review date and reviewer. **A portal asking us to stop is honoured immediately and the source is disabled, not throttled.**
- Fetch-side SSRF controls already documented in `docs/known-pitfalls.md` (resolve every hop, reject private/loopback/link-local ranges, manual redirect handling, byte caps) apply to every adapter without exception. Discovery multiplies the number of untrusted URLs the system touches by orders of magnitude.
- Documents fetched from portals are untrusted input end to end (base G-6): they may not trigger a tool call, a fetch, or a shell.

**Commercial note (not a spec):** T3 email ingestion is the only source that is simultaneously zero-ToS-risk, zero-crawl-cost, and instantly comprehensive per customer. It should be built first and marketed as the on-ramp; T1/T2 exist to serve customers who are not yet receiving alerts, and to build the shared corpus.

---

## 6. Module G — Requirement Traceability & Answer Reuse (P0-3)

**Purpose.** Make the compliance matrix a first-class artifact that exists the moment the TOM is locked, lives where bid managers work, proves nothing was dropped, and remembers what was written last time.

- **G-FR1 Matrix on lock.** Immediately after TOM lock (base A-AC5), a compliance matrix is generated deterministically from the TOM: one row per requirement, with requirement text, requirement level (mandatory / desirable / self-attestation), source anchor (`p.12 · Cl. 4.1(a)`), evidence-required text, and empty response/owner/status columns. **No Generator run required** — this is the standalone deliverable for teams who will draft in Word.
- **G-FR2 Unmapped-requirement count (the denominator).** The shredder emits, per document section, the count of requirement-bearing sentences that did **not** map to a matrix row, each individually listed and resolvable to `mapped | explicitly-not-a-requirement (user marked)`. A matrix cannot be marked complete while unmapped sentences remain unresolved. This is the deterministic answer to "risk of missing requirements" — coverage stops being an assertion and becomes a measurement (extends base ET-4 upstream).
- **G-FR3 Answer library.** Every approved response, keyed to the requirement it answered, is indexed with its criterion type, evidence documents, authority, and — where the outcome is known — the win/loss of the bid it shipped in. For a new requirement, the top matching prior answers are suggested with provenance (which bid, which date, which outcome) and must be **explicitly accepted** before entering a draft. Reuse is a suggestion with a receipt, never a silent paste.
- **G-FR4 Excel round-trip.** Export to XLSX; edit offline; re-import with a **row-level diff and explicit merge confirmation**. Row identity travels in a stable hidden key column. Requirement text, level, and source anchor are import-protected — an edited requirement cell is rejected as a conflict, because a re-imported spreadsheet must never be able to silently rewrite the locked TOM. Bid desks live in Excel; the product meets them there rather than fighting it.
- **G-FR5 Ownership and status.** Per-row owner, status (`not started / drafting / drafted / reviewed / approved`), and due date, integrated with base Module E roles, comments, and the audit trail.
- **G-FR6 Evidence binding.** A row binds to specific content-library documents with page anchors (base C5 citation chips). Expired evidence renders as expired at the row (base S8-D1 semantics) — the certification that lapsed is visible where the response is written, not only at export.
- **G-FR7 Single coverage figure.** Coverage is computed once, in one deterministic function, and every surface that shows a number reads it from there — matrix, export gate (base B-AC4/E-AC2), and dashboard. Per `docs/known-pitfalls.md`: four counters describing the same object will disagree.

### 6.1 User stories

**G-US1** As a bid manager, thirty seconds after locking the TOM I have the compliance matrix I would have spent a day building in Excel.
**G-US2** As a proposal manager, I can state exactly how many requirement sentences the RFP contained and where each one is answered.
**G-US3** As a writer, when I open a requirement I have written before, I see what we said last time, on which bid, and whether that bid won.
**G-US4** As a bid manager, I export to Excel, my SME fills column F on a plane, and I re-import without losing traceability.

### 6.2 Acceptance criteria

| ID | Criterion | Threshold | Method |
|---|---|---|---|
| G-AC1 | Requirement-bearing sentences in the RFP mapped to a matrix row or explicitly resolved | 100% before a matrix may be marked complete — hard gate | Deterministic gate on the unmapped set |
| G-AC2 | Requirement extraction recall on the annotated gold set | ≥ 95% | Gold-set eval (extends base A-AC1) |
| G-AC3 | Matrix rows rendering requirement level + source anchor matching `p.\d+ · Cl\.` | 100% | Deterministic validator |
| G-AC4 | XLSX round-trip fidelity: export → re-import with no edits produces a byte-identical matrix state | 100% | Automated test |
| G-AC5 | Re-import mutating requirement text, level, or anchor | **0** — rejected as conflict | Deterministic gate |
| G-AC6 | Suggested reused answers entering a draft without explicit user acceptance | **0** — hard gate | Deterministic gate + logs |
| G-AC7 | Reused-answer suggestions carrying provenance (source bid, date, outcome where known) | 100% | Deterministic validator |
| G-AC8 | Coverage figures agreeing across matrix, export gate, and dashboard | 100% (single-source function) | Automated test |
| G-AC9 | Time from TOM lock to a usable matrix | ≤ 60s p90 | Production telemetry |

---

## 7. AI vs. deterministic split (extends base §2.4 — normative)

| Concern | Owner |
|---|---|
| Fetching, parsing and normalising portal listings | Deterministic adapters |
| Deduplication / merge decisions | **Deterministic only** (exact ref match); fuzzy candidates surface as grouped suggestions, never merges |
| Feed inclusion / exclusion | **Deterministic only**, from user-authored named rules (G-9) |
| Feed ordering and relevance banding | AI, with cited matching past project |
| Opportunity summaries | AI, cite-or-drop |
| Eligibility-subset extraction from an NIT | AI, schema-allowlisted, confidence-scored |
| Depth-1 and Depth-2 eligibility verdicts on numeric/date/boolean criteria | Deterministic comparators — the same ones, at both depths |
| Requirement-sentence identification during shredding | AI, with a deterministic unmapped-sentence denominator that the human must resolve |
| Matrix generation, coverage counts, unmapped counts | Deterministic |
| Prior-answer retrieval and ranking | AI |
| Prior-answer insertion into a draft | **Human action only** |
| XLSX import conflict detection | Deterministic |

---

## 8. Error tolerance (extends base §3.2)

| ID | Error | Example | Severity | Tolerance | Mitigation |
|---|---|---|---|---|---|
| **ET-7** | **Discovery miss** — a qualifying tender never reaches the user | A state portal adapter silently breaks; nobody notices for six weeks | **Critical** — the only failure here with no natural feedback signal | F-AC1 backtested recall ≥ 95%; source-health incident on any zero-item deviation | F-FR5, F-FR12, G-9, EC-8 |
| **ET-8** | **Wrong merge** — two distinct tenders collapsed into one | Two packages from the same authority closing the same day merged; one is never seen | Critical | 0 (F-AC4) | Deterministic-only merge (F-FR6) |
| **ET-9** | **Feed noise** — the feed becomes another thing nobody reads | 300 items/day; the user reverts to Excel | High | ≤ 25 in-scope items/day/workspace; ≥ 60% rated worth a look | F-FR9–F-FR11, F-AC2, rule tuning in onboarding |

Discovery-side false positives (a non-relevant tender shown) are **cheap** — one line skimmed. Discovery-side false negatives are **existential to the module's value**. Every ambiguous design decision in Module F resolves toward showing more, ranked lower — never toward hiding.

---

## 9. Edge cases and fallbacks (extends base §8.1)

| ID | Case | Behavior |
|---|---|---|
| EC-8 | Source adapter breaks (portal markup change, endpoint moved) | Item-count deviation vs. trailing median raises an **incident**, not an empty feed; the feed renders a per-source coverage banner naming the degraded source and the last successful fetch. A silent zero is the ET-7 failure mode. |
| EC-9 | Portal rate-limits, blocks, or asks us to stop | Back off, then disable the source; notify affected workspaces that coverage for that portal is degraded and offer the T3 email path. Never rotate IPs, never evade (G-8/G-10). |
| EC-10 | Forwarded email is an aggregator digest containing many tenders | Parse into individual opportunities where structure permits; where it does not, create one item carrying the raw email and flag it for manual split — never drop the email. |
| EC-11 | Listing publishes no eligibility fields and the NIT is behind a login or a paid document fee | Depth-1 verdict is `Unknown — needs the NIT`, rendered as such with a clear next action. **Never inferred from the title.** |
| EC-12 | RFP requirement text spans a table cell, a footnote, or an annexure reference | The sentence still enters the unmapped denominator; unresolvable structures are listed for human resolution rather than dropped (G-FR2). |
| EC-13 | Re-imported XLSX conflicts with edits made in-app since export | Row-level three-way diff with explicit per-row resolution; no automatic last-write-wins. |

## 10. Rollback criteria (extends base §8.2)

| ID | Trigger | Action |
|---|---|---|
| RB-5 | Backtested recall (F-AC1) drops below 90% on the rolling replay set | Disable relevance ranking (feed reverts to chronological in-scope + excluded-visible), notify, RCA before re-enable |
| RB-6 | Any wrong merge detected in production (F-AC4 ≠ 0) | Disable grouping entirely; every record renders as its own opportunity until the merge path is fixed |
| RB-7 | Depth-1 hard-gate disagreement (C-AC7) exceeds 10% in a rolling 4 weeks | Suppress Depth-1 eligibility labels; feed shows `Unknown` until re-validated |
| RB-8 | Requirement recall (G-AC2) regresses > 2 points on the gold set | Pin the shredder to the last known-good prompt/model version (mirrors base RB-3) |

---

## 11. Screens (extends `docs/DESIGN_SPEC.md` §D)

New screens follow the existing design contract: tokens only, C1 sidebar, C2 dense tables, C4 verdict chips, C5 citation chips, C6 SLA chips, and default + loading (skeleton) + empty + error states for each.

| ID | Route | Module | Purpose | Key design ACs |
|---|---|---|---|---|
| **S14** | `/opportunities` | F | The daily feed: in-scope list with the three decomposed signals per row, Excluded bucket with live count, source-health banner, assignment control | **S14-D1** every excluded item names its causing rule; **S14-D2** the Excluded count is always visible from the primary feed, never behind a menu; **S14-D3** every row renders a resolvable source link + retrieval timestamp; **S14-D4** relevance renders as a band with its cited past project, never a bare number |
| **S15** | `/opportunities/:id` | F, C | Opportunity detail: normalized record, sources seen on, Depth-1 eligibility with deciding criteria, corrigendum history, actions (watch / assign / ingest) | **S15-D1** Depth-1 verdicts carry a provisional label and a "run full analysis" action; **S15-D2** possible-duplicate candidates render as a group, never merged |
| **S16** | `/opportunities/rules` | F | Rule builder: named deterministic rules with live match-count preview against the last 30 days | **S16-D1** saving a rule previews how many of the last 30 days' items it would have excluded, before saving |
| **S17** | `/tenders/:id/matrix` | G | Standalone compliance matrix: rows, owners, status, evidence bindings, unmapped-sentence panel, XLSX export/import | **S17-D1** the unmapped-sentence count renders as a blocking chip while > 0; **S17-D2** expired evidence renders danger tokens at the row; **S17-D3** import conflicts render a per-row diff requiring explicit resolution |
| **S18** | `/profile/gaps` | C | Credential-gap rollup: each missing/expired item with the count and aggregate value of open opportunities it blocks | **S18-D1** each gap names its blocked-opportunity count and links to that filtered feed |

---

## 12. Success metrics

**Module north star:** *qualified* opportunities acted on per workspace per week — an item that was surfaced, was eligible, and received a human decision (shortlist or skip-with-reason). It rises only when discovery, triage, and traceability all work; feed volume alone cannot move it.

| Metric | Target | Source |
|---|---|---|
| Backtested recall vs. partner bid history (F-AC1) | ≥ 95% | Replay harness — **the primary P0-1 gate** |
| Hours/week spent on portal monitoring, partner-reported vs. own baseline | ≥ 70% reduction (submitted pain data claims a 10–20 h/week ceiling) | Design-partner time study |
| In-scope items reviewed per day per workspace | ≤ 25 | Telemetry |
| Tenders reaching shortlist that Depth 2 later finds hard-ineligible | ≤ 10% | Depth-1/Depth-2 agreement |
| Time from TOM lock to usable compliance matrix (G-AC9) | ≤ 60s p90 | Telemetry |
| Matrix rows filled from the answer library (accepted suggestions) | ≥ 40% by the third bid on a workspace | Telemetry |
| Requirement sentences unmapped at submission | 0 | Deterministic gate |
| Model cost per workspace-day for Depth-1 triage | Logged and rendered in settings; alerting threshold per workspace | Cost telemetry (base §5.3) |

---

## 13. Build sequence

Sequenced so that each phase is independently demoable and the cheapest-legal-risk source ships first.

| Phase | Scope | Exit gates |
|---|---|---|
| **PH4a — Matrix first** | Module G: matrix on lock, unmapped denominator, XLSX round-trip, ownership. No new acquisition surface; depends only on the existing locked TOM. | G-AC1–G-AC5, G-AC8–G-AC9 pass; S17 design ACs pass |
| **PH4b — Email discovery** | Module F via T3 only: per-workspace inbound address, email parsing, dedup, rules, feed, digest. Zero crawling. | F-AC3–F-AC7 pass on email-sourced items; S14/S16 design ACs pass |
| **PH4c — Triage** | Module C delta: eligibility-only extractor, Depth-1 verdicts on feed items, profile-change replay, gap rollup. | C-AC6–C-AC11 pass; S15/S18 design ACs pass |
| **PH4d — Crawled sources** | T1/T2 adapters: NIC-stack adapter + GeM/CPPP, source registry with terms review, source-health incidents, corrigendum watch. | F-AC1 ≥ 95% on the replay set; F-AC5, F-AC8 pass; crawl-discipline audit (G-10) clean |
| **PH4e — Reuse** | Module G answer library with outcome linkage; requires shipped bids to index. | G-AC6, G-AC7 pass; ≥ 40% suggestion acceptance on the partner cohort |

**Sequencing rationale.** G before F because it needs no new external dependency and converts the base product's existing TOM into a standalone deliverable — it is the fastest path from spec to value. T3 email before crawling because it carries no ToS exposure, delivers per-customer completeness immediately, and lets the ranking and dedup logic be tuned on real volume before any crawler exists. Crawled sources last, once the feed they feed is already proven useful. F-AC1's backtest requires partner bid history — recruit for it during PH4a.

---

## 14. Assumptions register (veto these)

| # | Assumption | Confidence |
|---|---|---|
| 1 | Official machine-readable tender feeds (T1) exist for some but not all major portals; per-portal availability must be verified at build time and treated as revocable | Medium — **verify before committing PH4d scope** |
| 2 | Most state e-procurement portals run the NIC eProcurement stack, so one adapter family covers the long tail; adapter count, not portal count, is the estimating unit | Medium-high — sample-verify across ≥ 8 states before estimating |
| 3 | Design partners can supply 12 months of their own bid history for the F-AC1 backtest | Medium — without it, F-AC1 is unmeasurable and PH4d has no gate; secure it during PH4a |
| 4 | Customers already receive portal alert emails and will auto-forward them | Medium — if false, T3's value collapses and PH4b/PH4d swap order |
| 5 | ≤ 25 in-scope items/day/workspace is the noise ceiling before a feed stops being read | Low — tune against partner behaviour in PH4b |
| 6 | Depth-1 eligibility can be answered from listing fields plus a targeted NIT slice for the majority of tenders, without full ingestion | Medium — measure the escalation rate in PH4c; if most tenders escalate, the cost model for triage-on-everything needs revisiting |
| 7 | Bid desks will accept an in-app matrix if XLSX round-trip is lossless; they will not abandon Excel | Medium-high |
| 8 | Answer reuse needs ≥ 3 shipped bids per workspace before suggestions are useful | Low — PH4e gate is behavioural, tune on cohort data |

---

*— End of document —*
