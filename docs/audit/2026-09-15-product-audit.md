# TenderCraft product audit — 2026-09-15

**Scope:** the bidder product (`apps/web` + `services/engine`), judged against two outcomes: (1) find the most relevant tenders for the customer's business, (2) turn a tender into a submission-ready proposal with as little effort as possible.
**Method:** a live walk of production as the seeded test user (who lands in the Usha Martin workspace — see §4), four code traces (web journey, discovery engine, proposal pipeline, operations), and the repo's own test suites. Every claim below is either something seen on a production screen or cites `file:line`.
**Fixes shipped in this pass:** §11 lists nine, all verified (engine 1272/1272, deterministic branch coverage 100%, web 68/68, typecheck and lint clean, the hub nav browser-checked with zero console errors). None is committed; the diff is in the working tree.

---

## 1. Executive summary

**What works.** The discovery feed is real and live: 7,256 tenders swept from GeM, IREPS and eight other portals three times a day, deduplicated by reference, ranked into three bands with a one-sentence reason per row, gated by the customer's own rules and never by the system. For a manufacturer with a filled capability statement the top of the feed is genuinely on-target (steel wire rope, slings, IS 2266 — every row). The safety architecture is intact and tested: lock gate, comparators, cite-or-flag, transclusion, export gate, append-only audit, workspace isolation, 1,270 engine tests green, 100% branch coverage on the deterministic gates. Ingestion reads a whole GeM package including scanned pages, names the tender after itself, and the readiness hub is a good idea executed with care.

**What is fundamentally weak.** The product does not yet deliver either outcome end to end, and the reason is the same in both halves: **the system enumerates, the customer ranks.**

- *Discovery* stops at a three-value band. Seventy-two rows in the customer's feed are all "high"; there is no number, no composite, and the one calibrated figure the pipeline produces (model confidence) is discarded before storage. Value, geography, certifications, experience and deadline runway play no part in ranking. A pursued tender is a dead end: the documents are not fetched, the pursuit has no home, and the user downloads and re-uploads what the crawler already touched.
- *Proposal creation* fills the wrong form. The proposal skeleton is a constant — a 17-section MeitY IT-services packet — applied to every tender, so a wire-rope supply bid receives "Training & Capacity Building" and "Support SLA & O&M" sections and a technical score against an IT-services rubric. The extractor treats every sentence as a criterion, including instructions to bidders and blank declaration templates, so the customer faces 896 items "awaiting verification" and a Bid/No-Bid card that says **NO-BID** on a tender squarely inside their core product line because a *post-award* inspection clause was scored as a pre-bid eligibility gate. Getting from upload to a file is 16 + N clicks, two "generate" buttons, nine per-section approvals and a second human.
- *Buyer-facing correctness*, the product's stated licence to exist, had three false statements in the live draft: four current certifications printed as EXPIRED, the cover page reading "Submitted by: Bidder", and the letter of proposal naming the tender by its upload filename. Two are fixed in this pass; the third is a template problem (§7).

**Overall.** The product today is a strong compliance *engine* wrapped in a workflow that asks the customer to do the ranking and the triage the engine was built to do. The distance to the north star is not new capability — most of it exists — it is sequencing, classification and reachability. The highest-leverage work is (a) classify extracted requirements into gates, obligations, instructions and forms so verdicts and checklists stop being noise, (b) derive the proposal outline from the tender instead of a template, (c) chain upload → prepare → draft automatically, and (d) turn the feed's band into a scored, explained shortlist that auto-fetches documents on pursue.

---

## 2. Current user journey (as observed)

There is no signup. Access is by invitation, and an invitee who has no account cannot accept (`components/AcceptInvite.tsx:51-56`). Workspace creation is an org-admin action hidden in the sidebar switcher. First login on an empty workspace shows four KPI tiles (one hardcoded "Unlimited", `dashboard/page.tsx:98`) and an empty state whose CTA is *upload a tender* — not *tell us about your company*, which is what the feed and every verdict depend on (`dashboard/page.tsx:139-141` vs `:217-232`).

| Stage | What the user does | Clicks / screens | Observed friction |
|---|---|---|---|
| Tell us about the company | `/profile` (identity, financials, certs, experience) → `/capability` (statement, keywords, envelopes) → `/library` (docs, annual report, past bids) → `/prices` (GeM categories, no editor) | 4 screens, all hand-typed | Five stores, nothing inferred from uploaded documents; four fields displayed but not editable (`working_capital_cr`, `scope_tags`, `cert_no`, `dpiit_registered`); cert expiry left blank renders as EXPIRED downstream |
| Discover | `/opportunities` → Refresh → scan | 1 screen, 72+ rows | All rows "high"; no score; "Turnover required: none stated" on every IREPS row; 4,310 "in your feed" on one screen vs 867 "open" on the capability screen |
| Decide to pursue | Pursue → redirected to `/tenders/upload?pursuit=` → open each portal link, download, drop files | 1 + N external + 1 | Documents are not fetched even though the crawler already fetched the GeM bid document for eligibility (`ingest.py:517-519`); a pursuit that is not uploaded is invisible afterwards |
| Understand the tender | `/tenders/:id/readiness` | 1 screen, 34 identical decision blocks | No summary card (scope, value, deadline, EMD, documents required); every clause gets the same three-button decision + upload + note block, including "Bidders to quote Rate / No." |
| Bid / no-bid | Confirm k low-confidence items → "Analyze & match" (15–30 s) → `/tenders/:id/analysis` | k + 1 + (URL typed by hand) | Analysis, matrix, schedule fit, clarifications and the locked TOM were unreachable from any live-tender screen until this pass (§11) |
| Draft | "Generate proposal" (a link) → "Generate proposal document" (~2 min) | 2 | Two generates with one label; the per-criterion drafts `/prepare` already paid for never enter the document |
| Review | Edit / Approve × 9 narrative sections; flags list with no resolve action | ≥ 9 | Placeholder blocks, citation chips and attest/attach controls promised by the spec are absent (`ProposalDocument.tsx:30-101, 341-349`) |
| Export | "Compliance & export" → 2 stage approvals by 2 distinct users → "Export final documents" (no file) → back → "Download .docx" | 5, two humans | Solo SME must use admin override |

**Total, happy path: about 23 + k + m clicks across 7 screens with two people.** Five of the six tenders in the customer's workspace are still at `uploaded`; the sixth has a draft blocked by nine approvals.

---

## 3. Critical problems (P0)

1. **Bid/No-Bid is noise, and the noise is conservative in the wrong direction.** On GEM/2026/B/7876746 (wire rope slings — the customer's product) the card reads *NO-BID (conservative), 1 mandatory gate failed, 12/100, 4 Pass · 1 Fail · 30 Needs review*. The failed "gate" is *"Load test must be certified by competent person… certificate must be submitted"* — an obligation at pre-dispatch inspection, months after award. Root cause: `analysis.analyze` sends every criterion of every category through the profile evaluator (`analysis.py:104-109`); any mandatory `needs_review` forces the aggregate down (`eligibility.py:98-101`); instructions, GeM GTC boilerplate and blank declaration templates are extracted as criteria in the first place. A false NO-BID costs the customer a bid they would have won, which the feedback doc names as the single worst outcome.
2. **The proposal is the wrong document.** `SECTION_SPECS` is a fixed 17-section IT-services packet (`sections.py:45-90`). The tender's own forms, annexures and schedule never shape it; Form 12 hardcodes "no deviations" (`sections.py:249-261`) even when Module H found some; the technical score is measured against a MeitY rubric ("Team composition & key personnel 3.0/15") for a goods supply. For the customer that exists, the pre-drafted share of a usable proposal is ~10–15% and much of the rest is wrong-shaped.
3. **False statements in the draft.** Certifications with no expiry on file rendered "EXPIRED (no expiry recorded)" (`sections.py:212`, fixed); DOCX cover "Submitted by: Bidder" because `tenders.bidder_name` never existed (`proposal_routes.py:391`, fixed); the average-turnover transclusion can never fire because `assemble_compliance_pq` is called without `required_fys` (`proposal_routes.py:123-125`), so Form 1 prints "Required FY window not confirmed" while ₹3,582 Cr sits in the profile; the Letter of Proposal names the tender by its upload filename.
4. **Every tender lacks a deadline.** All six show "Deadline not recorded"; the SLA chip, dashboard sort and "closes in N days" are dead. Nothing ever wrote `tenders.deadline` from a document (the GeM bid document states `/Bid End Date/Time` on page one) or from the pursuit's `closing_at`. Fixed for new uploads in this pass; existing rows need a one-off backfill.
5. **Half the tender workflow was unreachable.** Analysis, matrix, schedule fit, clarifications and the locked-TOM view hung off `/tenders/[id]`, which was linked only for exported tenders (`tenders/page.tsx:133-134`). Fixed: the readiness hub now carries a tender nav.
6. **Regenerate destroys human edits and keeps approval stamps.** `do_generate_sections` upserts body/status/flags without touching `approved_at`/`edited_by`/`original_md` (`proposal_routes.py:155-176`), so an approved section regenerated stays "approved" with new AI prose and exports without the watermark (B-FR4 hole); Re-match likewise overwrites accepted reuse answers (`proposal_routes.py:63-72` vs `reuse_routes.py:196-204`).
7. **Verification volume is a wall.** 896 items "awaiting verification" across six tenders; the readiness hub renders an identical 3-button + upload + URL + note block for each of 34 items on one tender, including *"Bidders to quote Rate / No."* Root cause is the same as #1: no classification of what an extracted sentence *is*.
8. **No signup, no onboarding, and email alerts are dead in production.** `/login` says "Start free" in plain text; the empty workspace routes to upload; `/settings` reports "no mail server configured" because the engine has no `RESEND_API_KEY`, so the hourly digest cron sends nothing — and when it could, it dropped deadline and value from every line (`notify_service.py:48-49` read columns the row does not have; fixed).

---

## 4. Broken features and root causes

| Feature | Symptom | Root cause | Status |
|---|---|---|---|
| Tender deadline | "Deadline not recorded" on 6/6 tenders | No write path for `tenders.deadline` from document or pursuit | **Fixed** (new uploads); backfill pending |
| Cert validity in Form 1 | Valid certs printed EXPIRED | `bool(valid_to) and …` collapses "unknown" into "expired" (`sections.py:212`) | **Fixed** |
| DOCX cover | "Submitted by: Bidder" | Reads a column that does not exist | **Fixed** |
| Digest email | No "closes …" or value on any line | `_flatten` reads `deadline`/`value_display`; rows carry `closing_at`/`estimated_value`; test stub mirrored the wrong shape | **Fixed** + stub corrected |
| Sub-screens | Analysis/matrix/schedule/clarifications/TOM only via typed URL | Only linked from `/tenders/[id]` for exported tenders | **Fixed** (hub nav) |
| Turnover transclusion | Form 1 never shows the average | `required_fys` never passed (`proposal_routes.py:123`) | Open |
| Estimator / Score | "Estimate technical score" always suppressed | `outcomes` never written; cluster hardcoded `it-hardware` (`analyze_routes.py:18`) | Open — hide until data exists |
| `value_between` rule | Never fires on GeM rows | `estimated_value` column left null; parsed value lives only in `eligibility` jsonb (`db.py:1318-1325`) | Open |
| Model confidence | Cannot show "92% match" | Computed then dropped (`pipeline/relevance.py:122` → never stored) | Open |
| Rules engine | Coverage strip built around rules, no way to author one | `POST/DELETE /api/opportunities/rules` have no web caller | Open |
| GeM categories | Capability screen points to `/prices` to edit them | `POST /api/categories` has no UI | Open |
| Lock gate | `LOCK_BLOCKED` on unanchored criteria with nothing to edit | Hub lists only `priority=confirm`; no anchor editor; S4 rule ≠ server rule (`VerifyQueue.tsx:51-54` vs `types.py:96-97`) | Open |
| Export button | "Export final documents" produces no file | `POST /export` audits/harvests; bytes are on another page | Open |
| Settings | Tabs are decorative spans; approval chain names disagree with export stages; escalation thresholds static | `settings/page.tsx:20-37, 118-123` vs `ExportGate.tsx:32` | Open |
| Fuzzy matcher | C-AC5 has no eval | `prompts/eligibility-matcher.md` is a TODO; `evals/run.py:17` omits it | Open |
| Env docs | `.env.example` named `ANTHROPIC_API_KEY`; engine reads `GEMINI_API_KEY`; Resend vars undocumented | Doc drift (same class as the `GEM_CONNECTOR_URL` incident) | **Fixed** |
| Login claims | "Data stays in India" (stack is EU-hosted); "Start free — 3 analyses/month" (no signup, no tier) | Copy outran product | **Fixed** |
| Test account | Seeded test user's active workspace is the design partner's real workspace | Membership granted for demos | Open — decide deliberately |

Operational: BUILD-LOG stopped 2026-07-25 (96 commits since); CLAUDE.md still says Claude API on Vercel + Railway (reality: Gemini on Cloud Run); evaluate-engine migrations have colliding numbers 0005/0006; ~28 MB of demo-video renders and 194 Playwright dumps are tracked; the customer's tender PDFs sit untracked but un-ignored at the repo root.

---

## 5. UX friction

- **Two "generate" buttons with one label** (`ReadinessHub.tsx:396-403` is a link; the real generate is on `/proposals/:id`).
- **Two verification UIs** with different lock rules (S4 `/verify` vs the readiness fold-in) and **two analysis entry points** (`/analyze` vs `/prepare`).
- **Three compliance matrices** with three status vocabularies (S10 export gate, Module G workflow matrix, in-document matrix) and **seven "how done are we" numbers** (`submission.py:1-9` admits four disagreed on one screen).
- **Company data in five places**, none inferred from documents already uploaded (`library_documents.structured_fields` is extracted and never fed back).
- **Capability vocabulary in three screens** (profile keywords, capability standards, price-history categories) with a read-only note on the capability page pointing at a screen with no editor.
- **Every requirement gets the same decision block** regardless of kind; no summary card above the list.
- **Pursue has no home**: no pursuit list, no row state, no "you claimed this".
- **Errors by `alert()` and `window.prompt`** (`OpportunityFeed.tsx:528`, `ReadinessHub.tsx:193`); silent sweep failure (`OpportunityFeed.tsx:584-592`); engine errors surface as 404 or redirect (`export/page.tsx:24`, `readiness/page.tsx:34`).
- **Nine approvals + two-person chain** before a file exists; no approve-all; no solo mode.
- **French toggle covers ~3 screens** of 20; the seeded user landed in French on an Indian workspace.
- **Score page issues a rubric POST on every GET** (deterministic, but 3.5 s of latency for a number the user did not ask for).

---

## 6. Tender discovery assessment

**Architecture (verified).** Sources: GeM (crawled), BidAssist (licensed aggregator, notices on, awards gated), TED (FR). Sweep 3×/day, upsert on `(source_id, portal_ref_no)`, then per-workspace recompute for workspaces with members. Deterministic gate from user rules; turnover-only depth-1 eligibility from the GeM bid document; Gemini band (high/medium/low + one sentence) for the 40 soonest-closing stale rows per run, keyword band for the rest.

**Inputs used vs ignored in ranking**

| Input | Used | Note |
|---|---|---|
| Capability statement, keywords, GeM category names, IS standards | Yes | Merged since 09-14; the recovered IS 2266 tender proves it |
| Category codes / authority | Yes (deterministic) | BidAssist sectors are a different taxonomy, so GeM-shaped rules never hit them |
| Turnover | Eligibility signal only | Does not affect order; a `likely_ineligible` high sorts above a `likely_eligible` medium |
| Estimated value | **No** | Column null for GeM; `value_between` rule inert |
| EMD / ePBG / experience years | Parsed, shown, **not compared** | Profile has experience records; comparator says "turnover only" (`discovery.py:118`) |
| Certifications, MSE/Udyam status, geography | **No** | |
| Product-spec envelopes (diameter, grade…) | **No** on the feed | `spec_match` runs only post-upload |
| Bid document text | **No** | Model sees title/categories/authority only |
| Past bids / wins | **No** | |
| Model confidence | Computed, **discarded** | |

**Quality risks seen live.** 72 rows all "high"; "Turnover required: none stated" on every IREPS row; GeM ⇄ BidAssist duplicates shipped, not merged (`overlaps_source` is labelled by the connector and read by nothing); closed high-band rows keep their match rows and crowd the 100-row server page so fresh open rows are cut off before the client hides closed ones; the model budget (40 rows/run, soonest-closing first) leaves long-dated tenders on keyword bands for weeks; the feed's "4,310 in your feed" and the capability screen's "867 open tenders" describe the same workspace.

**Verdict.** A customer with a filled profile *does* open the app to relevant tenders with a reason each — that is real and rarer than it sounds. They do not get five; they get seventy-two equals. "92% match — value fits, one eligibility risk" is not possible from stored data today, and the PRD's F-FR11 currently forbids a decimal, so a composite score is a PRD amendment first. The missing pieces are small individually: store confidence; copy `estimated_value_inr` up to the column; add experience/EMD comparators from the already-parsed document; merge duplicates; exclude closed server-side; rank eligibility before band; auto-fetch the bid document on pursue so depth-2 runs without a manual upload.

---

## 7. Proposal creation assessment

**What is automated:** page parse and OCR, per-page criteria extraction with anchors, BOQ line items, spec parameter extraction, tender naming, per-criterion eligibility verdicts and per-criterion drafts (on click), nine narrative sections (on click), Form 1/6 tables from the profile, CV index from the library, cite-or-flag validation, export gate, DOCX render.

**What company knowledge reaches the document, and how:** identity fields and certifications into Form 1; top-5 experience rows into Form 6; library text chunks (lexical top-k, no pgvector) into drafts; readiness-pinned documents per criterion. **Not reached:** product specs, categories, capability keywords, line items, spec-match verdicts, clarifications, past-bid answers during generation (reuse is a manual per-section panel), and structured financials as prose (the drafter sees text chunks, not the profile).

**Against the north-star checklist**

| Capability | State |
|---|---|
| Parse documents accurately | Good; OCR path landed this week |
| Extract every requirement | Over-extracts: instructions, GTC boilerplate, blank templates all become criteria |
| Mandatory vs optional | Yes (requirement level) — but not gate vs obligation vs instruction vs form |
| Evaluation criteria & scoring method | Extracted as `evaluation_weight`; ignored by `weighted_score`; rubric is a fixed IT model |
| Compliance matrix | Three of them |
| Map requirements → sections | No: template is constant |
| Reuse company info | Partly (tables); prose is chunk-grounded |
| Reuse past proposals | Manual, per section, post-hoc |
| Draft responses | Yes, ~9,600 words; generic where evidence is thin |
| Identify missing info / ask only what AI cannot answer | Readiness list does this in spirit, but asks the same question for every kind of item |
| Detect contradictions / weak responses | Rubric flags short sections; no contradiction check (Form 12 "no deviations" can contradict Module H) |
| Completeness & compliance before submission | Yes (gate) — but mandatory coverage counts placeholders and instruction rows |
| Professional final document | DOCX exists; structure wrong for goods; cover/title defects (two fixed) |

**Verdict.** For an IT-services RFP the machine produces ~90% of the words and ~30–40% of the company-specific content; for a goods/BOQ tender ~10–15%, wrong-shaped. The single biggest gap is that the proposal's structure is a constant, not a function of the tender. Until the skeleton is derived from the tender's required forms, annexures, evaluation heads and (for goods) its schedule, every downstream investment — mapping, reuse, gates — fills in the wrong form.

---

## 8. Features to remove or simplify

| Remove / simplify | Why |
|---|---|
| Score estimate (`/proposals/:id/score` hero, `POST /estimate`) | Permanently suppressed by design (no outcomes are ever written). Hide until ≥30 outcomes exist; keep the rubric only if it is made tender-shaped |
| Two of the three compliance matrices | One artefact, one status vocabulary; the Module G workflow matrix can be a view of it |
| Six of the seven coverage numbers | `submission.compute` is the reconciled one; retire the rest from screens |
| S4 `/verify` as a separate screen | The readiness fold-in is the path users take; keep one confirm UI and one lock rule |
| `POST /analyze` as a separate entry | `/prepare` already runs it |
| Settings "Approval chains" and "Deadlines & alerts" | Static arrays with wrong stage names; remove until they drive anything |
| The French toggle on Indian workspaces | Three screens translated of twenty; hide until coverage is complete or a French workspace exists |
| Per-criterion drafts (`proposal_responses`) as a paid step | They never enter the document; either surface them as the requirement-by-requirement response the buyer marks, or stop paying for them |
| "Watch this tender" star + stage-watch button | Fold into pursue; a pursued tender is watched by definition |
| `/knowledge` (Learning) as a top-level page | Honest but empty for every customer for months; fold into the library as a panel |

---

## 9. Missing high-impact features

1. **Requirement classification** — gate (pre-bid eligibility), obligation (post-award), instruction (how to submit), form (a template to fill), technical spec (a line item). It fixes the verdict, the verification volume, the readiness hub and the compliance matrix in one move. Deterministic first (label patterns, section headings, declaration markers already detected by `drafting.template_placeholders`), model-assisted only for the residue.
2. **Tender summary card** at the top of readiness: scope, buyer, value, deadline, EMD/ePBG, bid type, documents required, evaluation method — all already parsed by the GeM connector for the feed and thrown away at upload.
3. **Tender-derived proposal outline** — forms/annexures named in the document become the sections; for goods, the schedule becomes a per-line technical compliance table fed by `spec_match`; SECTION_SPECS becomes the fallback.
4. **One automatic chain**: upload → extract → (auto-confirm when nothing is low-confidence) → prepare → draft, as a background job with a jobs table; buttons become "re-run".
5. **Scored, explained shortlist**: composite from stored model confidence + category hit + turnover margin + value-in-band + runway, with the reasons list the north star describes; PRD F-FR11 amended to allow it.
6. **Pursue fetches the documents** and starts the chain; a pursuits list shows every claimed tender and its stage.
7. **Profile inference from documents**: turnover from the annual report/CA certificate, cert expiry from the certificate, CIN/GST from the incorporation certificate — proposed with a citation, confirmed with one click.
8. **"Only you can answer these"** panel: the residue after classification and inference, phrased as questions, with the answer written straight into the draft.
9. **Approve-all and a solo-bidder mode** for workspaces with one member.
10. **Signup + guided setup** that starts with the company, not the upload.

---

## 10. Prioritised roadmap

| Priority | Problem | Customer impact | Proposed change | Effort | Recommendation |
|---|---|---|---|---|---|
| P0 | Verdict counts obligations/instructions as eligibility gates → false NO-BID | Lost bids; trust in the card collapses | Requirement classification; only gates feed the verdict; add a reasons + risks list | M (engine: extractor schema + `analysis.py` + `eligibility.py`; web: analysis card) | Do first |
| P0 | Proposal skeleton is a constant | Wrong document for goods; generic prose for services | Tender-derived outline; schedule → compliance table; SECTION_SPECS as fallback | L (`sections.py`, `proposal_routes.py`, `spec_service.py`, `ProposalDocument.tsx`) | Do second |
| P0 | 896 items to verify; identical decision block per item | Abandonment at the first screen after upload | Same classification; group by kind; instructions become a checklist, forms a "to fill" list | M (`readiness.py`, `ReadinessHub.tsx`) | With #1 |
| P0 | Regenerate keeps approvals, drops edits | Unwatermarked AI prose can export | Skip `edited_by` sections; reset approval on body change; never overwrite accepted reuse | S (`proposal_routes.py:155-176`, `db.py`) | Quick |
| P0 | Turnover transclusion never fires | Form 1 omits the one number every PQ asks | Derive `required_fys` from the extracted turnover criterion; pass it | S (`proposal_routes.py:123`) | Quick |
| P0 | Deadline backfill for existing tenders | Dashboard SLA dead for current pursuits | One-off SQL: `tenders.deadline` from linked `opportunities.closing_at` where null | S | Quick (production write — confirm first) |
| P0 | Mail dead in prod | Alerts feature is a promise | Set `RESEND_API_KEY`/`RESEND_FROM` on the engine service with `--update-env-vars` | S | Ops |
| P1 | Feed: band only, confidence dropped, value/eligibility not ranked | 72 equals instead of 5 | Store confidence; copy value to column; composite order; closed rows excluded server-side | M (`relevance.py`, `db.py:1429`, `ingest.py`) | After P0 |
| P1 | Pursue does not fetch documents | Manual download/re-upload; depth-2 never auto-runs | Fetch `document_urls` on pursue, start ingest, list pursuits | M (`opportunities_routes.py:287`, `tenders.py`, new list page) | |
| P1 | GeM/BidAssist duplicates | Double rows, double model spend | Merge on `overlaps_source` + normalised ref | S–M (`ingest.py`) | |
| P1 | No signup/onboarding | Cannot acquire a customer without hand-holding | Signup route; first-run checklist starting at profile; invite accepts without prior account | M (web) | |
| P1 | 16+N clicks, two humans | Solo SME cannot export | Auto-chain; approve-all; solo mode; export returns bytes | M | |
| P1 | Company data fragmented, nothing inferred | Re-typing what was uploaded | Profile inference with citations; one "Your company" screen | M–L | |
| P1 | Lock blocks on unanchored criteria with no editor | Dead end | Surface unanchored items in the hub with a page picker; align S4 rule with server | S (`ReadinessHub.tsx`, `VerifyQueue.tsx`) | |
| P2 | Rules and categories have no UI | Only the keyword toggle tunes the feed | Small rule builder; category editor on `/prices` | M | |
| P2 | Settings decorative | Confusing, contradicts export | Remove static sections; real tabs | S | |
| P2 | Score page: rubric POST on GET; estimator suppressed | Latency; a button that always fails | Compute on demand; hide estimator | S | |
| P2 | Three matrices, seven coverage numbers | Disagreeing figures | Consolidate to `submission.compute` + one matrix | M | |
| P3 | i18n partial; date formats inconsistent; `alert()`/`prompt` | Polish | Finish or hide FR; use `format.ts`; inline errors | S | |
| P3 | Docs/repo hygiene | Onboarding engineers | BUILD-LOG, CLAUDE.md stack line, migration numbering, untrack renders | S | |

---

## 11. Quick wins (done in this pass, uncommitted)

| # | Change | Files | Evidence |
|---|---|---|---|
| 1 | Tender deadline read from the document (`/Bid End Date/Time` on GeM, "Last date for submission" on NITs) as IST, and from the pursuit's portal `closing_at` when the document is silent (document first) | `app/deterministic/tender_meta.py`, `app/db.py`, `app/tenders.py` + tests | 5 new meta tests, 2 new pursuit tests; deterministic branch coverage stays 100% |
| 2 | Certificate with no expiry on file → "Validity not recorded — add the expiry date to the vendor profile", never EXPIRED | `app/sections.py` + test | `test_pq_sheet_never_calls_an_undated_certification_expired` |
| 3 | DOCX cover names the bidder from `vendor_profiles.legal_name` | `app/proposal_routes.py` | existing docx tests green |
| 4 | Digest email lines carry "closes …" and the value again; route test stub now uses the real row shape and asserts both cues | `app/notify_service.py`, `tests/test_notify_routes.py` | assertions would have failed before the fix |
| 5 | Readiness hub links to Requirements, Eligibility analysis, Compliance matrix, Schedule fit, Pre-bid clarifications | `components/ReadinessHub.tsx` | browser-checked locally: nav renders, link navigates, 0 console errors; screenshot `.playwright-mcp/readiness-hub-nav.png` |
| 6 | Login copy: "Data stays in India" → "Nothing leaves without human approval"; "Start free" → "Access is by invitation" | `app/(auth)/login/page.tsx` | typecheck/lint clean |
| 7 | `.env.example` names `GEMINI_API_KEY`/`GEMINI_MODEL`/`GEMINI_TIMEOUT` (what the engine reads) and `RESEND_API_KEY`/`RESEND_FROM` | `.env.example` | names verified against `pipeline/client.py`, `app/mailer.py` |
| 8 | Upload `title` and `pursuit_id` declared as multipart `Form()` fields. As bare `str` defaults FastAPI bound them as query parameters, so both were empty on every upload ever made: tenders fell to their filename and the pursuit → tender link (portal reference, authority, closing date) never fired. Confirmed independently after the parallel Codex review (`docs/reviews/2026-09-15-codex-product-audit.md` §V B1) reported it | `app/tenders.py` + multipart contract test in `tests/test_pursuits.py` | `test_upload_title_and_pursuit_id_arrive_as_multipart_form_fields` fails on the old binding |
| 9 | Section approval now requires the `draft` permission, the same gate as editing. A `viewer` could previously sign every narrative section and clear the export watermark (B-FR4). Also reported by the Codex review §V and by this audit's own pipeline trace | `app/proposal_routes.py` + `tests/test_authz.py` | `test_a_viewer_cannot_approve_a_section` → 403 |

Note on #8: fix #1's pursuit-deadline fallback and the whole `_apply_pursuit_context` path were unreachable in production until #8 landed — a downstream feature hardened for weeks against a value a binding bug guaranteed would be missing. The Codex review's four §D items (verdict confidence reachability, and three others) were not re-verified here and remain open questions.

Cheap and not done here (need a decision or a production write): deadline backfill SQL for the six existing tenders; `RESEND_API_KEY` on the engine service; moving the seeded test user out of the customer's workspace; the regenerate/approval fix (#4 in the roadmap, small but touches the B-FR4 guarantee — wants a `/review`).

**Verification run:** `uv run ruff check .` clean · `uv run pytest --ignore=tests/isolation` 1272 passed · `--cov=app/deterministic --cov-branch --cov-fail-under=100` 100.00% · `pnpm typecheck` · `pnpm lint` · `pnpm test` 68 passed · local `/tenders/:id/readiness` as FIX-1: nav present, `Eligibility analysis` navigates, console errors 0.

---

## 12. Ideal future experience

**Open the app → five tenders, each with a score and three reasons → two are marked "worth bidding" with the one risk each → click Pursue → documents are fetched, read and classified while you get coffee → the readiness page opens on a summary card (what, who, when, how much, what to attach) and a short list of questions only you can answer → answer them → the proposal is 70–80% written in the tender's own structure, with your certificates, turnover and past projects already in the right forms → review, approve all, export.**

Concretely, the customer journey collapses to: **profile once (mostly inferred from three uploaded documents) → daily shortlist → pursue → answer 5–10 questions → approve → download.** Everything the current product does — extraction, verdicts, cite-or-flag, gates, audit — still runs; it just runs *for* the customer instead of *after* the customer.

The one question to keep asking of every screen: *does this make it easier for our customer to find the right tender and win it?* Today the answer is "yes, if they do the ranking themselves". The roadmap above is the work to make it "yes".
