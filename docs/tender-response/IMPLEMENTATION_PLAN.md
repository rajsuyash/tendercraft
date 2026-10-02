# Tender response & compliance — implementation plan (§27 D)

**Status:** proposed, 2026-10-02 · nothing scheduled · **Decision owner:** human
**Reads with:** `DATA_MODEL.md`, `ARCHITECTURE.md`

## 0. Ordering principles

1. **The evaluation harness comes first.** Every later milestone states its acceptance as a
   number on the 12-tender corpus; without the harness those numbers cannot be produced, and a
   scorer written after the code it scores tends to agree with it.
2. **Retention before intelligence.** Nothing downstream (quote verification, re-extraction on
   corrigenda, pack export, Type D fill) works without stored originals and page text.
3. **Deterministic value before model value.** The GeM bid-document parse (51% of requirements),
   Type B template fills (7 families need no model) and the copy-forward checks deliver most of
   the safety at zero model cost.
4. **Phases of ≤ ~5 files.** Where a milestone is larger it is split into numbered phases, each
   verified and summarised before the next starts (user rule; `CLAUDE.md` "one milestone at a time").
5. These milestones are an extension of the bidder surfaces (`apps/web`, `services/engine`) —
   not a third product. The F13 wall is untouched; nothing here may import from `apps/evaluate`
   or `services/evaluate-engine`.

Every milestone's Definition of Done is `CLAUDE.md`'s: `pnpm typecheck`, `pnpm lint`, `pnpm test`,
`cd services/engine && uv run ruff check && uv run pytest`; `/verify-api` for engine routes;
`/verify` + screenshots for web; `/evals` for prompt/pipeline changes with a token/cost line;
the isolation suite on a **local** Supabase stack for every new table (`known-pitfalls.md`
"isolation suite points at production by default"). New screens have no `design_ref`; their
S-ids are proposed to the human, as S21 was (`docs/feedback/usha-martin.md`).

## 1. Milestones at a glance

| # | Milestone | Depends on | Model? | Value |
|---|---|---|---|---|
| M-j | Evaluation harness + golden loader | — | no | every later gate is measurable |
| M-a | File retention, page store, DOCX/MSG/image ingest, content classification | — | R for leftover pages | originals exist; filenames stop lying |
| M-b | GeM bid-doc deterministic parse + v1.1 requirement extraction + quote verification | M-a, M-j | R | requirement register UML can trust |
| M-c | Company vault + evidence library + admin verification UI | M-a | no | facts with provenance and validity |
| M-g1 | Copy-forward & validity checks on uploaded documents (C01–C05, C14, C17) | M-a, M-c | no | catches the 6 historical incidents early |
| M-d | Submission manifest planner + evidence bindings + historical guidance | M-b, M-c | R proposes | "what must we submit, and why" |
| M-e | Missing-information queue | M-d | no | MISSING_INFORMATION becomes a workflow |
| M-f | Template engine: Type B + Type D DOCX fill | M-c, M-d | no (R only on variant ties) | most declarations generated |
| M-g2 | Full compliance validator (C06–C13, C15, C16) + matrix read model | M-f | no | one source of "ready" |
| M-h | Pack export, hash-bound approvals, response_status | M-g2 | no | a downloadable, checked pack |
| M-k | Type C drafting under cite-or-flag + model tiers | M-d | W | technical compliance statements |
| M-i | Corrigenda versioning + invalidation | M-b, M-h | R | changes after lock handled safely |

## 2. Milestones

### M-j — Evaluation harness (first)

- **Goal:** score any pipeline output against the analysed corpus, and prove the scorer can fail.
- **Scope:** `services/engine/evals/tender_response/` — `golden.py` (loads
  `requirements|submission_documents|mapping/*.json`, `template_candidates.json`,
  `missing_information_patterns.json`, `evidence_library.json` from `$TC_GOLDEN_DIR`, never
  copied into the repo), `match.py` (page-range + token-overlap matcher), `metrics.py` (the eight
  metrics in ARCHITECTURE §7), `run.py` (wired into `evals/run.py`), synthetic fixtures for CI.
- **Acceptance:**
  - golden-vs-golden scores 1.0 on every metric for all 12 tenders;
  - three corrupted controls go red: (a) drop every 10th mandatory row → mandatory recall ≈0.90;
    (b) paraphrase requirement text with no word overlap → matcher reports misses, not hits;
    (c) shift every page anchor by +1 → recall collapses. Assert the corruption landed before
    reading the score.
  - vault-as-of filter: for ECL_GEM-2024-B-4818673 (bid end 22-04-2024) no fact first seen in a
    2025/2026 document is visible.
  - CI runs the synthetic fixtures only; the corpus run is local/manual and prints its input count.
- **Risks:** the golden set is agent-produced (quote suspects, ONGC lacks a bid document); the
  matcher is untested code in the trust path — hence the controls.
- **Decided (§H2, 2026-10-02):** yes — the analysed corpus is the scoring golden set.

### M-a — Retention, page store, wider ingest, classification

- **Goal:** every uploaded byte is stored once, every page has persisted text, every page has a
  content-derived role.
- **Phase a1 (≤5 files):** migration `0049_files_pages.sql` (`files`, `pages`, Storage bucket
  policy); `app/storage.py` (put/get by sha256, workspace prefix); `app/ingest.py` (persist pages,
  accept DOCX incl. tables, MSG, JPG/PNG); `app/tenders.py` (store before parse; `Form()` binding);
  tests.
- **Phase a2:** migration `0050_tender_documents.sql` (`tender_documents`, `document_versions`,
  `page_roles`); `app/deterministic/page_roles.py` (rule classifier: GeM header, GTC version,
  Integrity Pact heading, UML letterhead/signature block); `pipeline/page_classifier.py` +
  `prompts/page_classifier.md` (R tier, enum output, leftovers only); `jobs` kind `ingest`; tests.
- **Acceptance (corpus, via M-j):**
  - every buyer page listed in each `_text/<slug>/manifest.json` is stored with text; page counts
    match `pdfinfo` for all 12 tenders;
  - all 9 "ATC"-named UML bundle files + `Steel policy.pdf` (`03_initial_findings.md` §E1) classify
    as `seller_*`, and the 3 genuine buyer ATCs (ECL-6929440, ECL-7055356, MCL) as
    `buyer_requirement` — 13/13;
  - SAIL `Tender Docs.pdf`: pp1-6 `buyer_requirement`, pp7-11 `buyer_format_filled`;
  - a fault-injected classifier error leaves pages `unclassified` and surfaced, never dropped.
- **Verify:** `uv run pytest tests/test_ingest*.py tests/test_page_roles.py`; `/verify-api` on
  `POST /api/tenders/ingest` (201 + envelope; 400 `UNSUPPORTED_FORMAT` only for genuinely
  unsupported types); isolation suite on local stack for the three tables.
- **Risks:** OCR budget per package. Storage region is EU now, per §H3 (move to an India region
  pre-production-scale); UML corpus storage in production is confirmed (§H4).

### M-b — Requirement register

- **Goal:** a v1.1 requirement register with exact anchors, verified quotes and conflicts.
- **Phase b1:** `app/deterministic/gem_bid_doc.py` (port of `gem-connector/app/document.py`,
  extended to dates, schedules/quantities, upload slots, buyer-added terms, embedded ATC);
  parity test against the connector's golden fixtures; migration `0051_criteria_v11.sql`
  (columns in DATA_MODEL §2.4, `requirement_conflicts`).
- **Phase b2:** `pipeline/extractor.py` + `prompts/extractor.md` → per-section calls, v1.1
  schema; `app/deterministic/quote_check.py` (≥90% words, 100% numbers on cited range);
  `deterministic/lock.py` extended (unclassified/illegible pages, open conflicts block lock);
  `VerifyQueue.tsx` shows the retained source page.
- **Acceptance (M-j, hold-out split):**
  - mandatory bid-stage requirement recall **≥0.98** on the 10 GeM tenders that contain a GeM bid
    document (ONGC has none — scored on its tech spec/BEC only), reported per tender;
  - the deterministic parser alone reproduces the golden EMD, ePBG, turnover, MSE/startup and bid
    end values for those 10 tenders with **0 numeric mismatches**;
  - overall requirement recall ≥0.90, precision ≥0.80; every prediction with `quote_fidelity`
    verbatim/reflowed passes the quote check or is marked REQUIRES_REVIEW;
  - the 3 golden `conflicts_with` pairs and SAIL's single-part vs two-envelope conflict are
    proposed (recall 4/4); false-conflict rate reported, not gated (no labels for it);
  - fault injection: invalid JSON / timeout → page marked for human review, no crash, no invented row.
- **Verify:** `/evals` extractor (+ cost line); `uv run pytest tests/test_gem_bid_doc.py
  tests/test_quote_check.py tests/test_lock.py`; `/verify` on `/tenders/:id/verify`.
- **Risks:** per-section calls cost more tokens than per-page; table-heavy tech specs
  (`condensed_table` 79 rows) are where recall will fail first.

### M-c — Company vault and evidence library

- **Goal:** facts and evidence with provenance, validity and verification status, administered
  by UML.
- **Phase c1:** migration `0052_company_facts.sql` (`company_facts`, evidence columns on
  `library_documents`, `evidence_bindings`); `app/deterministic/fact_keys.py` (registry);
  `app/vault_service.py`; `tools/seed_vault.py` that imports `company_facts.json` +
  `evidence_library.json` **into the UML production workspace** (§H4 decided 2026-10-02:
  production storage approved) with status DOCUMENTARY/UNCONFIRMED as recorded.
- **Phase c2:** `db.get_profile_context` reads facts; parity test that
  `deterministic/facts.py::decide_requirement` verdicts are identical on legacy tables vs facts
  for the FIX-2 fixture and the seeded UML workspace; legacy tables → views.
- **Phase c3 (web):** `/vault` admin screen: facts grouped by category, source page preview,
  Verify/Reject with reason, expiry timeline; sensitive values masked.
- **Acceptance:**
  - 53/53 facts and 37/37 evidence rows load; the 3 UNCONFIRMED facts can never fill a variable
    (unit test drives each through the resolver);
  - validity computed: NABL TC-5016 shows expired after 11-02-2026; API-9A conflict
    (26 vs 29 July) surfaces as a fact conflict, not a silent pick;
  - no sensitive value appears in any prompt payload, log line or API response field (grep test
    over a recorded run);
  - parity test green; isolation suite green on local stack.
- **Risks:** two writers to one concept during c2 (pitfall) — views, not copies.

### M-g1 — Early checks on uploaded documents

- **Goal:** the copy-forward and validity checks, runnable on any uploaded UML document before
  the generator exists (they are also the eval for generated output later).
- **Scope (≤5 files):** `app/deterministic/compliance/identity.py` (C01, C14 with field roles),
  `dates.py` (C02), `validity.py` (C03, C04), `variants.py` (C05), `duplicates.py` (C17); tests.
- **Acceptance:** run over the archived UML submitted documents of all 12 tenders:
  **6/6 known incidents flagged** (MCL ×2 stale bid numbers, ONGC wrong-bid local content,
  NMDC-7682164 "Coal India" lowest-price certificate, ECL-6119954 wrong land-border branch,
  ECL-7055356 local-content date) and **0 false positives** on the other tenders, including the
  ~8 past-contract numbers in provenness evidence; the SAIL post-deadline dates flagged
  REQUIRES_REVIEW (deadline itself is "not established"); a check that has never failed is
  shown failing on a mutated copy first.
- **Verify:** `uv run pytest tests/test_compliance_*.py --cov=app/deterministic/compliance
  --cov-branch` = 100% branch.

### M-d — Submission manifest planner

- **Goal:** for each tender, the list of documents to submit, each answering what / why / which
  clause / reuse / info complete / evidence / who signs.
- **Scope:** migration `0053_manifest.sql`; `app/deterministic/manifest_rules.py` (obligatory
  items, folder slots, coverage); `pipeline/manifest_planner.py` + prompt (R groups and proposes
  `response_type`, logged to `ai_decisions`); `app/manifest_service.py`; `/tenders/:id/plan` screen.
- **Historical guidance:** `app/deterministic/historical_prior.py` — per requirement type × buyer
  family, which `doc_kind`/template family UML used; surfaced as suggestions only.
- **Acceptance (M-j, hold-out):** submission-document recall **≥0.90** against golden UML
  documents (origins UML generated / reusable / tender-specific / buyer-format-filled, mapped to
  `doc_kind`); every mandatory bid-stage requirement covered by an item or a file-less reason
  (C07 = 100%); evidence mapping accuracy ≥0.85; historical suggestions never produce a
  `confirmed` binding (asserted).
- **Risks:** golden "documents" include bundles; scoring on constituents, not bundles.

### M-e — Missing-information queue

- **Scope (≤5 files):** migration `0054_information_requests.sql` (freeze-on-answer trigger as
  0038); `app/deterministic/info_requests.py` (gap → grouped templated question, seeded from the
  16 MIP patterns); routes; `/requests` screen; resolution re-runs affected items.
- **Acceptance:** replaying the 12 tenders with the as-of vault, the queue raises an ask for
  ≥0.80 of golden MIP occurrences of kind `information_request` that were knowable at bid time
  (EMD basis MIP-001, data sheets MIP-003, buyer ATC retention MIP-005 …); no question text is
  model-written; answering one grouped ask clears every blocked item it names (integration test).
- **Note:** post-award patterns (MIP-002, MIP-010) become scheduled reminders, not bid blockers.

### M-f — Template engine (Type B + Type D)

- **Phase f1:** migration `0055_templates.sql`; `app/templates/render_docx.py` (python-docx,
  `{{var}}` replacement, content controls); `app/deterministic/variables.py` (resolution order
  tender → fact → evidence → admin, never historical); seed the 7 deterministic families
  (TMP-002/003/004/005/006/007/008) as `draft` variants for a UML admin to approve.
- **Phase f2:** Type D: `app/templates/buyer_format.py` — DOCX buyer formats filled by label match
  (Integrity Pact particulars, SAIL Word annexures); PDF buyer formats → particulars sheet +
  REQUIRES_REVIEW item. Never replaces a prescribed format with a UML template.
- **Acceptance:** for each of the 7 families, rendering against each golden instance's tender
  reproduces the instance's variable values with **0 copy-forward errors** (C01/C02/C05 green),
  including the corrected land-border branch; template selection accuracy ≥0.90 vs
  `template_candidates.json`; `values` + `statement_sources` written for every variable; a
  missing variable renders a visible placeholder and raises an information request (C09 red).
- **Human decision:** UML approves each variant's boilerplate before it is selectable.

### M-g2 — Full validator and matrix read model

- **Scope (≤5 files):** `compliance/formats.py` (C06), `coverage.py` (C07, C08 attestations),
  `consistency.py` (C09, C10, C11), `gtc.py` (C12), `conflicts.py`+`unsupported.py` (C13, C15,
  C16); `compliance_runs/results` migration; status roll-up; matrix read model replacing
  `matrix_rows` writes.
- **Acceptance:** ECL-7055356 replay: C11 flags the no-deviation vs Deviation Letter conflict;
  C12 flags the turnover-category EMD exemption against GTC v1.28; C04 flags NABL; SAIL replay:
  C13 blocks on the open bid-structure conflict. Unified "ready": `deterministic/submission.py`
  and `export_gate.py` consume the same results (the audit's C3 defect cannot recur — one test
  asserts readiness=ready ⇒ export_gate=pass on 50 generated states). 100% branch coverage.

### M-h — Pack export, approvals, status flow

- **Scope:** `app/pack_export.py` (ZIP 01–10, manifest-derived filenames, XLSX register and
  matrix, signature checklist, audit export); generalise approvals to `document_approvals`
  (hash-bound); `tenders.response_status` transition function + audit; `/tenders/:id/pack` screen.
- **Acceptance:** export blocked (409 envelope, zero bytes) while any blocking result exists;
  editing any generated document after approval makes the approval stop counting (test);
  pack contains no file twice (C17) and no source filename; `10_Audit_Trail` lets a reviewer walk
  one statement → requirement → page → fact → evidence → source file for every Type B variable.
- **Out of bounds:** uploading to GeM (G-1). The pack ends at a download.

### M-k — Type C drafting and model tiers

- **Scope:** `pipeline/client.py` gains `tier` (reasoning/drafting) and provider config;
  `pipeline/section_drafter.py` reused for TMP-013 technical compliance statements with
  `spec_parameters` as the only numeric source; `prompts/tech_compliance.md`.
- **Acceptance:** unsupported material fact rate **0%** on drafts for the 3 TMP-013 instances and
  the 7 MOIL schedules; every number is a transclusion; injection cases (instruction text planted
  in a tech spec) produce no tool call and no off-schema field; `/evals` with cost line; a model
  switch changes `prompt_sha`/`model_id` in the cache key (re-drafts rather than skipping).

### M-i — Corrigenda

- **Scope:** `app/deterministic/corrigendum_diff.py`; staleness propagation; status regression;
  notification. Uses `document_versions` from M-a.
- **Acceptance (synthetic — the corpus has no formal corrigendum):** replay ECL-7055356's
  `Modified Annexure-X.pdf` as a corrigendum to the ATC's embedded Annexure-X → exactly the RS 25
  rows change (200/240/260 mm), FLC 29 mm does not; a synthetic deadline extension clears the
  SAIL-style C02 flag; a contradictory synthetic clause opens a corrigendum conflict; all
  dependent approvals stop counting.

## 3. Decisions recorded 2026-10-02

| # | Question | Decision | Rationale | Consequence |
|---|---|---|---|---|
| H1 | Model provider routing — code is Gemini-only, `CLAUDE.md` names Claude | Delegated by the human to the orchestrator. Reasoning tier = `claude-opus-5` (adaptive thinking, effort `high`, server-side refusal fallbacks `fallbacks: "default"` with beta `server-side-fallback-2026-07-01`) for page classification leftovers, requirement extraction, submission planning, variant ties and compliance adjudication. Drafting tier = `claude-haiku-4-5`, for Type C prose and routine wording only — never compliance decisions. Tier → model via env vars `TC_MODEL_REASONING` / `TC_MODEL_DRAFTING`. | Opus is the strongest available model for the decisions §2.4 reserves to reasoning; Haiku is cheap and scoped to prose with no decision authority, consistent with the deterministic-decides rule. | `pipeline/client.py` gains a tier-routed Claude path (Python `anthropic` SDK) behind the single model module; existing Gemini callers (feed relevance, KB classifier, current extractor/drafter) stay unchanged until a parity eval says otherwise. The env var names go into `.env.example` when M-b/M-k add them. M-j's harness additionally measures `claude-sonnet-5` against Opus for high-volume per-page extraction on cost per tender vs. mandatory recall — the cheaper model is adopted only if the eval shows no recall loss. M-k is no longer blocked on this decision. |
| H2 | Golden set as evals — may the 12-tender analysis be used, where does it live | Yes — the analysed corpus is the scoring golden set. | The only way M-j's acceptance numbers can be produced is against real analysed tenders. | Stays outside the repo (gitignored `tender_analysis/`), read via `$TC_GOLDEN_DIR`. |
| H3 | Storage region/residency for client originals — Supabase is `eu-north-1`, PRD §9 wants India | EU region now (current Supabase + Cloud Run); move to an India region once live. | Matches the existing deployment; residency only becomes concrete once originals are retained, and that is not a reason to block starting M-a. | Recorded as a pre-production-scale task, referencing PRD §9 — must happen before real customer data volume grows. |
| H4 | Whether the UML corpus may be stored in production at all | Yes — the UML corpus, originals and vault may be stored in production. | UML is the confirmed design partner; retained originals and the vault need real data to be useful. | `tools/seed_vault.py` seeds the UML production workspace directly; open question 15 (which internal documents must never enter the system) still gates what gets imported from `company_facts.json`/`evidence_library.json`. |
| H5 | GeM upload automation | Confirmed — GeM upload stays manual (G-1/G-8). | Reaffirms an existing guardrail rather than opening a new one. | The product exports a pack plus an upload checklist; nothing here builds toward portal automation. |
| H6 | PDF rendering: inside the engine image vs a separate renderer | Delegated to the orchestrator. LibreOffice headless (`soffice --headless --convert-to pdf`) inside the engine image, run as a job stage; no separate renderer service. | Avoids standing up a new service for one conversion step; the engine already runs job stages (M-a). | Ceiling: image size and cold start. Split into its own service only if measured cold start or memory hurts. |
| H7 | New screen ids for `/vault`, `/requests`, `/tenders/:id/plan`, `/tenders/:id/pack` | Delegated to the orchestrator. New screens take ids S22+ (S19–S21 already used), built from `design/tokens.json` and the C1–C6 components. | Keeps numbering collision-free and reuses the existing design system rather than inventing new chrome. | DESIGN_SPEC §D/§E/§H rows are proposed to the human (the spec is sha-pinned; agents never edit it); `/design-review` has no row to check until accepted. |
| H8 | Retire `matrix_rows` once the read model ships | Delegated to the orchestrator. Yes — M-g2 introduces the read model over compliance results; `matrix_rows` becomes read-only for one release, then dropped in a later migration. | `matrix_rows` is an editable matrix users may currently rely on; a hard cutover risks losing in-flight edits. | One release of read-only coexistence before the drop migration. |

## 4. Open questions for the UML administrator (gathered from the reports)

1. Is naming the compiled upload bundle "ATC"/"ATC1"/"ATC Doc" a habit? Does the GeM "ATC
   compliance" slot receive that bundle or the buyer's ATC? (`03_initial_findings.md` G1, G9)
2. For the 9 tenders without a separate buyer ATC: was it embedded in the bid document, or not
   retained? Will you retain the buyer ATC and GTC from the portal at bid time? (MIP-005, MIP-012)
3. ECL-GEM-2025-B-7055356: where is the Deviation Letter for FLC 29 mm, and was it withdrawn,
   accepted or rejected? Can the clarification-round files (submitted 21-02-2026) be exported? (MIP-006, MIP-011)
4. ECL-GEM-2025-B-6929440: which BIS IS 1855 endorsement (No.70 or No.71) was uploaded?
5. MCL: were the stale-bid-number `.docx` declarations corrected, or was `local.pdf` uploaded?
6. ONGC: is the wrong-bid local-content page in `API 9A CERT.pdf` a misfile? Was a Factory
   Licence submitted? Is the API-9A licence (expiring 29-Jul-2026; certificate vs record differ
   by 3 days) renewed?
7. Was NABL TC-5016 (expired 11-02-2026) renewed? Please upload the current certificate.
8. SAIL: was the 25-02-2026 deadline extended? Where is the Proprietary Certificate? Is there a
   renegotiation letter for the 27-02-2026 rate?
9. When will the FY2025-26 turnover/net-worth certificate be available?
10. Which EMD-exemption basis should be claimed now that GTC v1.28 has no turnover category
    (BIS licence holder? CPSE?) — and is the stored GTC excerpt to be retired?
11. Who are the current authorised signatories, and which bank account (ICICI vs IndusInd) goes
    to which buyer?
12. Is the local-content percentage fixed per product line (60% on ECL rope, 50% on ONGC)?
    Who certifies it when the value threshold needs a cost-auditor certificate? (MIP-007)
13. The incorporation date reads 1886 on the PAN scan; please confirm 22-05-1986 from the CIN.
14. Oil India: was there a populated BOQ beyond the placeholder CSV?
15. Which internal documents (price sheets, SO worksheets, internal emails) must never enter
    the system? (commission notes are present in at least two tenders)

## 5. What this plan does not promise

- A measured accuracy. Twelve tenders from nine buyers, two with award evidence, one non-GeM
  and one without its GeM bid document are enough to catch regressions and known incidents,
  not to quote recall to a customer.
- Corrigendum handling validated on real data (none in the corpus).
- Any automation of the GeM portal.

## Decisions the brief did not cover

- Extend `criteria` and `library_documents` rather than add parallel Requirement/Evidence tables
  (lock gate, matrix and retrieval already key on them).
- Port the GeM parser into the engine instead of calling the connector (residency + two `app`
  packages).
- Put the eval harness and early copy-forward checks (M-j, M-g1) ahead of the planner.
- Add field roles (`current_tender_ref` vs `historical_ref`) — the corpus showed past-contract
  numbers that a naive bid-number check would flag.
- Treat signature/stamp/notarisation as human attestations, not verifiable checks.
