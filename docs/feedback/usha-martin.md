# Usha Martin Limited — design-partner feedback

**Status:** received, unanswered · **Received:** 2026-08-07 · **Source:** email + process
document from UML following a live demo
**Decision owner:** human sign-off required before any of §Sequencing is built
**Owner decisions, 2026-08-07:** answer the CRM ask with in-product routing first; time-box a
feasibility spike on historical prices rather than commit or park; document and plan only.
**Open for the owner, 2026-08-29:** a BidAssist/Nexizo partner feed has been licensed and its
connector built but left disabled — it needs a ruling on G-8 (does "no authenticated
acquisition" reach a paid vendor's own API key?) and someone to read the partner agreement
before any of this data is shown to UML. `docs/discovery/source-bidassist.md`.
**Half-answered 2026-08-29** (G-8 ratified, feed sweeping for opportunities);
**the other half is now the only thing between UML and a ten-portal price history.**

**Open for the owner, 2026-09-03 — one contract read, and ask 5 gets nine more portals.** The
price screen is wired to the licensed feed end to end (§ask 5 below) and ships **switched off**:
`registry.py`'s BidAssist row carries `display_reviewed=""`, the award sweep declines by name,
and the screen says so. That field is the partner agreement, expressed as code. Reading it for
our own workspace was never in doubt; **showing it to UML, who are not the licensee, is what
has never been checked** — and it is a commercial licence, so GeM's §8 posture does not carry
over. Set a date in that field and the whole thing is live; nothing else is pending.

This is the first entry in `docs/feedback/`. The repo had no convention for recording what a
customer actually said — design-partner language is already load-bearing in the discovery PRD
(F-AC1's backtest, F-AC2's weekly partner rating sample, PH4e's ≥40% acceptance gate) with no
file behind it. The form here follows `docs/multi-market.md`, which is the house shape for
*a client said something and it changed the architecture*.

## Who UML is, and why they are not this PRD's persona

Usha Martin Limited manufactures steel wire rope. They are registered on GeM under ten product
categories, nine of them rope against a named standard and one unrelated:

Wire Rope per IS 4521 / API Spec 9A (ONGC) · MIG Welding Wire · Stranded Steel Wire (Black Wire
Rope) · Winding and Man-Riding Haulage Ropes for Mines, IS 1855 · Haulage Purposes, IS 1856 ·
Wire Rope Slings and Sling Legs, IS 2762 · Round Strand Galvanised Rope for Shipping, IS 2581 ·
Suspension Ropes for Lifts, Elevators and Hoists, IS 2365 · General Engineering Purposes, IS 2266.

**`tendercraft-PRD.md` §1 targets P1/P2/P3 — people who write proposals.** A bid manager at a
services firm wins by what the narrative says, which is why the product's centre of gravity is
Module B: cite-or-flag, transclusion, the watermark, the export gate.

UML does not write a proposal. **UML selects a catalogue item and prices it.** Their bid is
won or lost on three questions the product currently cannot answer — can we make this exact
rope, do we have it listed on GeM already, and what did this item last sell for. Module B is
nearly irrelevant to them and Module D is suppressed by its own data gate.

That is not a criticism of the PRD; it is a segment boundary, and it should be conscious. A
commodity manufacturer is a different product than a proposal writer, and three of UML's five
asks live in a module that does not exist. **Whether that module gets built is a decision about
which segment TenderCraft is for** — see assumption 6.

## The five asks, verbatim

Quoted, not paraphrased. A paraphrased requirement is a requirement we invented.

1. **GeM Tender Lead Identification & CRM Integration** — *"The system should identify relevant
   tender opportunities from the notification emails received from GeM and automatically create
   a corresponding GeM Tender Lead in CRM. Currently, the relevant tenders are identified
   manually and circulated to the respective Zonal Heads."*
2. **Tender Specification & Manufacturing Capability Validation** — *"The system should analyse
   the tender specifications and validate them against UML's manufacturing capabilities and
   product specifications. Any mismatch or deviation should be identified at an early stage,
   enabling the concerned team to take corrective action or seek clarification before bid
   submission."*
3. **Catalogue Availability & Creation** — *"Catalogue creation is one of the critical
   activities before bid submission. The system should identify whether the required catalogue
   for each tender schedule is already available or can be created, based on the required rope
   specifications and technical parameters."*
4. **Identification of Additional Documents / Post-Technical Evaluation Requirements** — *"After
   the technical evaluation of a bid, GeM may require additional documents or clarifications.
   The system should monitor the tender status and identify such requirements as soon as they
   are generated on the portal, enabling the concerned team to respond within the stipulated
   timeline."*
5. **Historical Price Analysis — Key Requirement** — *"This is one of the major pain areas,
   particularly for single-party and limited tenders. The system should be capable of
   identifying and analysing the historical prices of the respective scheduled items for the
   last five years."*

## What is actually built

Measured by reading the code on 2026-08-07, not estimated.

> **Updated 2026-08-14.** Everything with no dependency on UML, GeM or a permission letter is
> now built. Asks 2 and 3 are answered end to end; ask 1's routing half is answered. Asks 4 and
> 5 and ask 1's *acquisition* half remain blocked on things only someone else can supply —
> see §Sequencing, whose steps 2–4 are still unsent asks.
>
> **Updated 2026-08-16, verified live 2026-08-24.** Asks 4 and 5 were reopened and are now
> partly built — **the 2026-08-07 refusal was too broad.** It was the CAPTCHA-gated
> `/view_contracts` that is closed; `bidplus.gem.gov.in` publishes the award ladder and the
> evaluation stage on a public, un-gated surface, which is how both now work with no login and
> no CAPTCHA bypass. Two things did NOT change and still gate the asks as UML worded them:
> **the document request itself is still behind the seller login** (we detect the stage, never
> the letter), and — at the time of that check — nothing ran on a timer.
>
> **Updated 2026-08-24: the timer exists.** `POST /internal/cron/{digest,watch}` authenticate
> Google's OIDC token (`app/cron_auth.py`) rather than a Supabase session, because these jobs
> have no user behind them, and two Cloud Scheduler jobs now call them — the digest hourly on
> IST business hours, the stage watcher twice a day. Both fan out across the workspaces that
> opted in and survive a per-workspace failure. So ask 1's *"automatically"* and ask 4's
> *"as soon as they are generated"* are answered as far as a public portal page can answer
> them. **The seller-login limit is unchanged and is not an engineering problem.**

| # | Ask | Status | Evidence |
|---|---|---|---|
| 1 | Lead identification → CRM, circulated to Zonal Heads | **Routing built; acquisition half still blocked** | Feed, connector, relevance banding and the rules gate were already live. **Added 2026-08-14:** `PATCH /api/opportunities/{id}` now enforces workspace membership on an assignee and can clear one, and the feed renders an Owner column and a watch star (`components/OpportunityFeed.tsx::Routing`). *Circulated to the respective Zonal Heads* is answered with no CRM. **Still missing:** inbound email (M11), which needs three forwarded GeM alerts from UML. **Added 2026-08-16:** outbound alerting — `deterministic/notify.py` (band threshold governs the inbox, never the feed), `mailer.py` with Resend primary and SMTP fallback, `GET/POST /api/notifications/{settings,dispatch}`. So a relevant tender does now email a human; it reaches them from our crawl, not from GeM's alert email, and **only when something calls `dispatch`.** |
| 2 | Spec vs manufacturing capability | **Built, and its output now goes somewhere — 2026-09-03** | **Pre-bid clarifications (step 2 of their own flow) shipped:** `deterministic/clarification.py` turns the deviating and unreadable parameters `spec_match` already computes into one question per parameter, folded across the schedule lines it covers; migration 0038 `tender_clarifications` records each through to the buyer's reply; S21 `/tenders/:id/clarifications`, linked from S20. The comparator had been naming these since August — `action_parameters` is documented at its own definition as "the pre-bid clarification trigger" and S20 rendered the word "Clarify:" beside them — with nothing to do with them. **The rule the feature is shaped around:** the bidder's capability never appears in the question, because GeM publishes a buyer's clarification answers to every bidder on the tender, so a query naming the plant's range hands it to a competitor and concedes non-compliance before the bid opens. It lives in `rationale`, workspace-internal and RLS-scoped, pinned at both the unit and live-database layers. We do not post to GeM (G-1/G-8): `sent` records that the bidder posted it. · Comparator itself: `deterministic/spec_match.py` (interval intersection → `match / deviation / equivalent / unknown`), `deterministic/spec_params.py` (registry + units + `allows_equivalent`), `pipeline/spec_extractor.py` (schema carries no verdict field), `spec_service.py`, migration 0029. UI: `/capability` records the envelope, `/tenders/:id/schedule` shows the fit. |
| 3 | Catalogue availability per tender schedule | **Built** | `deterministic/boq.py` finds the header row deterministically — no header found → zero line items and a manual-entry prompt. `tender_line_items` carries schedule ref, item ref, quantity, uom and a row-level anchor; technical criteria become line items too, because most GeM rope bids state the spec in NIT prose. Per line: `PUBLISHED` / `CAN BE CREATED` / `DEVIATION — CLARIFICATION NEEDED` / `NOT ASSESSED`. |
| 4 | Post-technical-evaluation document requests | **Built, both halves — 2026-08-24.** Stage from the public portal; the request itself from the customer's own forwarded mail | `deterministic/stage_watch.py` (pure: first sighting is never an alert, only forward moves alert), connector `GET /bid-status`, engine `POST /api/opportunities/watch/check`, migration 0034, watch star in `OpportunityFeed`. Live 2026-08-24: `GEM/2026/B/7876746` → `bid_awarded` + deep link, no login. **What it is not:** it is the alarm clock, not the letter — the clarification lives behind the seller login (G-1/G-8), and every rendered message says so. **Also:** the check is a button, not a poller. |
| 5 | Five-year historical prices per scheduled item | **Award history built; the five-year window is not** | `deterministic/price_history.py` (median not mean; unit rate emitted only for single-category records), connector `GET /bid-results`, engine `GET /api/price-history` + `POST /api/price-history/refresh`, migration 0033, `/prices` screen. Live 2026-08-24: real ladders with seller, rank, MSE flag and L1/L2 prices. **Date window added 2026-08-25**, closing the first gap: `from_date`/`to_date` (ISO) on `/bid-results`, `/api/price-history` and `/refresh`. GeM's `byEndDate` was in our payload all along, sent blank. Measured live — unfiltered returns 2026-08-24, `2023-01-01..2023-12-31` returns 2023-12-30, and a future window makes GeM's OWN `portal_total_matching` read 0. This mattered more than "a filter was missing": the sweep is newest-first and capped, so without a window the older years were **unreachable**, not merely unfiltered. ~~**Gap still open:** GeM's full-text search matches any word.~~ **Closed 2026-08-25, at the source rather than after it.** `param.searchType` takes a second value: `exact` matches the WHOLE category field instead of OR-ing the words. Same window, same two-portal-requests-per-row cost, measured live: `fullText q='wire rope'` → 10 fetched, **0** kept; `exact q='Steel Wire Rope'` → 6 fetched, **6** kept, every one carrying a ladder, spanning 2023–2026. This was never only a precision problem: the sweep is newest-first and capped, so under full text the budget was spent on rows that were then discarded and the older years were **unreachable** — the same failure the missing date window had, one level up. Shipped as `search_type` on the connector's `/bid-results`, `ingest.refresh_awards` and `POST /api/price-history/refresh`, plus **migration 0036 `workspace_categories`** to hold the names, because `exact` is case-sensitive and whole-field and only works with a string GeM itself wrote. **2026-08-29: a second award source exists but is not wired in.** The licensed BidAssist feed publishes award ladders across ten portals — 55 of 100 sampled awards carry more than one bidder, deepest 12 — which is reach the GeM connector structurally cannot have. It does **not** close the five-year ask: sampled award history runs 2025-12 → 2026-08. `services/bidassist-connector` `GET /awards` is built and proven live; routing it into `deterministic/price_history.py` is deliberately a separate slice, because the two sources disagree about MSE (BidAssist publishes none — `mse: None`, never `False`) and about whether a rank exists at all, and a price screen that blends them owes the user a note saying which portal each rung came from. **That slice is built, 2026-09-03 — and all three disagreements turned out to be schema problems, not display ones.** Migration 0037 makes `mse` and `rank` nullable (`not null default false` would have had this product state that a named real company is not an MSE), adds `awarded` to carry the winner where no ladder position was published, and adds `award_date` + a generated `observed_date` so a contract date is never written into the bid-close column the five-year window reads. `to_award` prefers a published rank and falls back to the `awarded` flag — never to price order, because the cheapest loser is not L2 unless somebody said so, and `undercut_pct` would otherwise be a fabricated spread. The screen names the portal per ROW, read off the host-qualified reference rather than a lookup table. `POST /api/price-history/refresh` asks both sources in the two different ways they accept — GeM by query, the feed by sweep — and the scheduled sweep keeps the feed current, because a feed has no query a user could type. **It ships switched off** pending the licence read: `registry.display_reviewed` is blank for BidAssist, the sweep declines by name, and the screen says only GeM was read. Still does NOT close the five-year ask on its own — this source's history starts 2025-12. |

**What is live today and worth telling UML in the reply.** Depth-1 eligibility is parsed
straight off the GeM bid document, deterministically, with **zero model calls and zero OCR** —
minimum average annual turnover, MSE/startup relaxation, EMD, ePBG, estimated bid value,
contract period, and years of past experience required (`services/gem-connector/app/document.py`,
69 tests, three template variants pinned by golden fixtures). For a GeM bidder that is the
eligibility half of ask 2 already working. It does not touch the technical half, which is the
half UML asked about.

## What the portal will and will not give us

`docs/discovery/source-gem.md` did this analysis for the bid listing on 2026-07-30. Two of
UML's asks turn on extending it.

> **Answered 2026-08-24, and the paragraph below was half wrong.** The guardrail refusal is
> real and permanent — we will never log in to UML's GeM account. But "ask 4 is a refusal"
> conflated the *constraint* with the *ask*. Two things were never checked:
>
> 1. **Is the stage public?** Yes. `b_buyer_status` on the un-gated listing carries the
>    lifecycle, so the stage watcher shipped with no login (0034).
> 2. **Is the request itself public?** No — now measured, not assumed. GeM publishes 34 fields
>    per bid and none is a clarification, corrigendum or document-request field
>    (`source-gem.md` §10). So the refusal below is confirmed *for that half*.
>
> What neither answered is that a third route existed the whole time: **the customer's own
> inbox.** GeM emails the seller the request; a forwarded email involves no credential of ours
> and no page we are not allowed to read. Shipped as `POST /api/inbound/email` + migration
> 0035. It was blocked on two things that turned out not to block: a provider choice (solved by
> signing the raw body ourselves, so any provider works) and never having seen a sample email
> (solved by a parser built to be wrong — classification routes, it never discards).
>
> **Live 2026-08-24.** `inbound.aisewak.com` receives on Resend and a real email has gone
> through the whole path — classified, bid reference extracted, deadline read, action raised.
> UML's side is one Outlook rule to `<their-token>@inbound.aisewak.com`.
>
> **The remaining honest limit is narrower than "unbuildable":** we see the request when UML
> forwards it, which is as fast as their mail rule, not as fast as the portal.

**Ask 4 is a guardrail refusal, not a backlog item.** Post-submission bid state — technical
evaluation outcome, a request for additional documents, a clarification window — lives behind
the **GeM seller login**. G-1 forbids portal credentials and G-8 forbids authenticated
acquisition, and neither is a policy we can weigh against a feature request: they are the
reason a government buyer can be sold the evaluate product at all (F13). We will never log in
to UML's GeM account and read their bid status, and we should say that plainly rather than
leave it in a backlog where it reads as "coming soon".

> **Superseded in part, 2026-08-16.** What follows is true of `view_contracts` and remains
> the reason we will never touch it. It was wrong as a claim about *ask 5*: the conclusion
> "there is no version of ask 5 that goes through the portal" generalised one refused endpoint
> to the whole portal. `bidplus.gem.gov.in/bidding/bid/getBidResultView/<id>` publishes the
> award ladder with no CAPTCHA and no login, and that is what shipped. The lesson is narrow
> and worth keeping: **a refused endpoint is not a refused portal** — enumerate the other
> surfaces before writing a capability off, which is what §Sequencing step 4 asked for and
> what nobody had done when this paragraph was written.

**Ask 5 was probed, and the portal route is refused.** `gem.gov.in/view_contracts` is public and
robots-clean — but **both of its search forms require a CAPTCHA** (`captcha_entered1/2`,
encrypted client-side via `POST /view_contracts/encryptCaptcha`), verified 2026-08-07 through
our own `GuardedFetcher`. `docs/discovery/PRD.md` §0 names *no CAPTCHA bypass* as a non-goal in
the same breath as no authenticated acquisition. This is a rule we wrote, and it is the rule the
evaluate product's credibility with a government buyer rests on. There is no version of ask 5
that goes through that endpoint. Full write-up: `docs/discovery/source-gem-contracts.md`.

**The route that works costs nothing and UML already owns the data.** They are the seller on
every contract they won — those award values are their own records. Uploaded, they land in
`past_bids` (migration 0027), whose `outcome` is user-supplied *by design* because
*"we cannot see an award notice"* (`app/past_bids_routes.py:155`). The same corpus is what
`deterministic/suppression.py` is waiting for: Module D withholds every score estimate until ≥30
comparable outcomes exist (D-AC4). **Ask 5 and the suppressed estimator are the same data
problem, and UML can solve both by uploading their own history.** State the limitation honestly
in the reply — it prices *their* past bids, not the market's, so it will not show what a
competitor bid.

Two things must not happen here. Do not buy a commercial GeM data feed to answer this before
UML has committed (assumption 7) and before their own history has been tried — it is ~$200/mo
for something option one may cover for free. **Priced 2026-08-25: the real figure is ~$1,000/yr
(BidAssist), not ~$200/mo.** The conclusion holds and the argument weakens — at $83/mo this is
not a spend to refuse on cost, it is one to refuse on redundancy, because about 70% of the
columns it sells are already read by the connector and its award data carries ONE awardee where
we read the whole L1..Ln ladder. What it would genuinely add is non-GeM portal coverage, which
is why §Sequencing step 2b asks UML where else they bid before anyone signs anything. And do
not take their GeM login "just to export
it": G-1 forbids us holding a portal credential, and a human at UML exporting a spreadsheet is
the same data with none of the exposure.

> **Overtaken by events, 2026-08-29 — the feed was bought, and two of the four sentences above
> are now measurably wrong.** A Nexizo/BidAssist partner API key issued to DONNA AI LABS
> arrived and was probed live. Full review: `docs/discovery/source-bidassist.md`; connector:
> `services/bidassist-connector` (built, **disabled**, pending human sign-off).
>
> * **"its award data carries ONE awardee" — false.** 100 award rows carried 328 bidder rows;
>   55 awards have more than one bidder, 51 of those an explicit rank, deepest ladder 12. It
>   publishes L1..Ln. The redundancy argument was resting on this and it does not hold.
> * **"about 70% of the columns are already read by the connector" — the wrong measurement.**
>   The overlap that matters is not columns, it is **portals**, and 57% of the sampled feed is
>   portals we do not touch at all: ireps.gov.in is the single largest at 46%, ahead of GeM's
>   43%, then Telangana, AP, Haryana, SAIL, Coal India, Rajasthan ×2 and CPPP.
> * **What survives, and is now the live question:** ~8 months of award history (sampled
>   `postingDate` 2025-12 → 2026-08), against an ask that says five years. Ask 5 as UML worded
>   it is still not answered by this source. Their own contract history remains the only route
>   to the older years, and it still un-suppresses Module D, so **step 2 is unchanged and still
>   unsent.**
> * **Two new blockers, neither of them technical:** G-8 forbids authenticated acquisition and
>   a vendor API key needs a human ruling on whether that rule was ever about vendors; and the
>   partner agreement — which governs whether this data may be shown to UML, who are not the
>   licensee — has not been read by anyone.

**The §8 reproduction clause governs both, and is already answered.** GeM's copyright policy
reads *"Contents of this website may not be reproduced partially or fully without due
permission in writing in advance from the GeM SPV."* The exposure is **republication, not
acquisition**, and `source-gem.md` §8 already sets the posture: store and display **facts, not
expression**; deep-link the prose and the documents; keep raw snapshots as an internal audit
record. A price, a quantity, a date, a buyer and a category code are facts, and they are
exactly what a price-history feature reads. **The existing doctrine covers ask 5 without
amendment** — which is worth noticing, because it means the constraint that looked like the
blocker is the one thing already resolved.

~~**Send the permission letter.**~~ **Closed 2026-08-25: the owner's legal team reviewed the
copyright position and cleared the current use.** The facts-and-deep-links posture stays — see
`source-gem.md` §8, which now records why it is worth keeping on its own merits rather than as
a legal hedge.

## The two findings that collapse work

**UML's inbox is a better feed than our crawler.** GeM routes new-bid notifications to sellers
by their registered category mapping (`source-gem.md` finding 7). UML is a registered seller in
ten categories, so **they already receive, pre-filtered, the feed we crawl and then rank**. For
this customer the email path is not a fallback — it is higher fidelity than relevance banding,
because GeM's own category mapping beats our keyword stems.

One correction to guard against, since it is the tempting claim: the email path removes
*acquisition* risk, **it does not avoid §8** (`source-gem.md:225`). Facts-and-deep-links applies
to a forwarded email exactly as it applies to a crawled listing.

**Asks 1 and 4 are the same pipe.** GeM emails the seller the new-bid alert *and* the
post-evaluation clarification request. One inbound-email path, with a message classifier
choosing between them, answers both — and for ask 4 it is the **only** legal route, because the
alternative is the seller login we will not use. Two of the five asks collapse into one
milestone that was already specced.

## What asks 2 and 3 actually require

A data model that does not exist. Sketched here so the roadmap is honest about size; the full
treatment belongs in a `tendercraft-manufacturer-PRD.md` with a Module H numbered in house
style, **written only if UML converts.**

- **Three tables.** `product_specs` (`spec_kind ∈ envelope | catalogue`, `parent_envelope_id`,
  `gem_catalogue_id`), `tender_line_items` (schedule ref, item ref, quantity, uom, row-level
  anchor), and a **typed-EAV** `spec_parameters` (`param_key`, `kind`, `unit`, `num_min`,
  `num_max`, `allowed_values`, `raw_text`, `confidence`). A point and a range are the same row:
  a required 20 mm is `num_min = num_max = 20`; a manufacturing envelope of 6–60 mm is
  `6..60`. Fixed columns (`diameter_mm`, `construction`, `core_type`…) die on the second
  customer and are 80% NULL on the first, where NULL would have to mean both *not applicable*
  and *unknown* — the one distinction this comparator must never blur. jsonb cannot be
  branch-covered, and `app/deterministic/` is CI-gated at 100% branch.
- **The comparator is interval intersection**, in `app/deterministic/spec_match.py`. States:
  `match | deviation | equivalent | unknown`. Roll-up is conservative in the shape `recommend()`
  already uses — any deviation → deviation; any unknown or equivalent → needs review. **A
  missing parameter is always `unknown`, never a deviation.** A false "we cannot make this"
  costs UML a bid they would have won, which is the only outcome here worse than saying nothing.
- **The model extracts; it never decides.** `pipeline/spec_extractor.py` returns typed
  parameters whose `param_key` is a JSON-schema **enum of registry keys** — that is the G-6
  allowlist — and its schema carries **no verdict field at all**. This is deliberately unlike
  `CRITERION_EVAL_SCHEMA`, whose `model_verdict` still decides every non-numeric criterion at
  `app/analysis.py:53-66` behind a 0.75 gate. `"or equivalent"` is detected in Python from
  `raw_text`, never model-reported: letting the model set the field that softens its own
  verdict is the `is_financial` bug in `known-pitfalls.md`, repeated.
- **BOQ parsing is additive.** `parse_spreadsheet_pages` is untouched, so criteria extraction
  and the unmapped-sentence denominator never notice the feature exists. A new
  `deterministic/boq.py` finds the header row deterministically; **no header found → zero line
  items** and a manual-entry prompt, because a guessed line item is worse than none. The prose
  path matters more than the spreadsheet one — most GeM rope bids state the spec in NIT text —
  so a `category='technical'` criterion also becomes a line item.
- **Generic schema, rope-seeded registry.** `deterministic/spec_params.py` holds the canonical
  keys, units and synonyms. Domain knowledge is data. `6x36` never becomes a column name.

The smallest slice that demonstrates both asks is one screen: a grid, one row per schedule
line, one column per parameter, each cell carrying the requirement, UML's capability and a
clickable anchor (`BOQ.xlsx · Schedule-A · row 14`) — and per line, **Published (SKU-4471) /
Can be created / Deviation — clarification needed**. That is asks 2 and 3 in UML's own words.

> **Built 2026-08-14** as `/tenders/:id/schedule` (S20, `components/ScheduleFit.tsx`), with
> `/capability` (S19) as its input side. **Two PRD divergences to ratify**, per CLAUDE.md's
> rule that reality contradicting the PRD is proposed, not silently drifted:
> (a) S19/S20 are new screen ids — S15/S16 were already the opportunity detail and rules screens
> in `docs/discovery/PRD.md` §Routes;
> (b) routing reuses the existing `PATCH /api/opportunities/{id}` rather than the
> `POST /api/opportunities/:id/assign` and `/watch` that the discovery PRD §Routes sketches for
> S15 — one endpoint that already existed and already had the ownership guard, instead of two
> new ones doing the same write. Columns are the union of parameters actually read, so a
> schedule stating three things does not render a dozen empty ones. Two things the screen says
> out loud, because both are claims we would otherwise be making silently: **"Published means
> recorded by you"** — we never read UML's GeM catalogue (G-1/G-8) — and **a parameter nobody
> recorded reads as `NOT ASSESSED`, never a deviation**, which is why `unknown` renders neutral
> rather than borrowing the amber that means needs-review. The screen gates nothing.

> **Extended 2026-09-03 — S21, pre-bid clarifications**, `/tenders/:id/clarifications`
> (`components/ClarificationPack.tsx`), linked from S20. **A third divergence to ratify on the
> same terms:** S21 is a new screen id with no reference render in `docs/DESIGN_SPEC.md` §D, so
> `/design-review` has no S21 row to check and cannot pass or fail it. It is built from
> `design/tokens.json` and the existing C2/C3/C5 components; the §D/§E/§H rows are proposed to
> the human rather than written by an agent, exactly as the spec's own sha-pin requires.
>
> Three things this screen says out loud, for the same reason S20 says two:
> **(a) we do not post to GeM** — "I posted this on the portal" records what the bidder did,
> the same shape as "Published means recorded by you";
> **(b) the question is written, not generated** — every sentence is a format string over the
> comparator's typed output, because a pre-bid query goes to a public buyer over the client's
> name and becomes part of the tender record;
> **(c) an empty list is only as complete as the recorded capability** — a parameter nobody
> recorded reads as not assessed, so "nothing to ask" is not a clean bill of health.
>
> **What it deliberately does NOT do.** An answer is recorded beside the lines it settles and
> changes no verdict by itself. The plan had a phase for re-running `spec_match` when a reply
> arrives; the reply is free text from a buyer, so acting on it automatically would mean a model
> reading untrusted prose and moving a compliance verdict — the exact shape §2.4 forbids. A
> human decides what a reply means, and the screen says so.

## Their ten categories are the asset, and four of them are worth what nine are not

Added 2026-08-25, after `searchType=exact` turned a category name from prose into a key.

UML listed their ten registered categories in their own words. Those words were probed against
the portal one spelling at a time, and the result is the reason the name has to come from GeM
rather than from the customer:

| UML's category | GeM's own string | awarded |
|---|---|---:|
| Wire Rope per IS 4521 / API 9A | `Steel Wire Rope` | 10 |
| MIG Welding Wire | `MIG WELDING WIRE` | 43 |
| Wire Rope Slings, IS 2762 | `Wire Rope Sling` | 2 |
| Round Strand Galvanised, IS 2581 | `Galvanized Steel Wire Rope` | 1 |
| Stranded Steel Wire (Black Wire Rope) | — | — |
| Mines winding / man-riding, IS 1855 | — | — |
| Haulage, IS 1856 | — | — |
| Lifts and hoists, IS 2365 | — | — |
| General engineering, IS 2266 | — | — |

**Five of nine matched nothing**, and that is the finding rather than a disappointing yield.
`exact` is whole-field and case-sensitive, so those five are not absent from GeM — they are
filed under a string nobody here has seen. `Wire Rope` returns 6 and `wire rope` returns 1;
the difference between a category with history and a category that looks dead is one capital
letter. This is why migration 0036 verifies a name when it is stored and why `verified_at`
is nullable rather than a flag defaulted to true.

Two things follow, and neither is an engineering task:

1. **Ask UML for their category names as GeM writes them** — a copy-paste from their seller
   dashboard, not a retyped list. This is one line added to §Sequencing step 2's email, which
   is already unsent.
2. **The names can also be READ rather than asked for.** A full-text sweep for `rope` returns
   GeM's own category strings on every record, and harvesting the single-item ones surfaced
   `Polypropylene Ropes as per IS 5175` (137 awarded), `Manila Ropes (V5) ISI marked to IS
   1084`, `Sisal Ropes - IS 1321`, `Winding Ropes 20 mm Dia`, `18mm STEEL WIRE ROPE` and
   `Un-Galvanized Round Strand Steel Wire RopeØ 24 mm Make: Usha Martin / Bharat Wire Ropes`
   — the last of which **names UML in the buyer's own specification.** A suggest endpoint over
   that harvest is the obvious next slice and is deliberately not built yet: it should be
   shaped by what UML sends back in (1), not by a guess about what they will recognise.

**A category is worth more than a price history.** The same stored name filters the feed at
the source, which is ask 1's ranking problem answered with GeM's category mapping instead of
our keyword stems — the thing finding 7 says beats us. Nothing yet reads `workspace_categories`
on the feed side; that is a small change and a deliberate one to make separately.

## Sequencing

1. ~~Spike `/view_contracts`.~~ **Done 2026-08-07. Refused (G-8, CAPTCHA)** —
   `docs/discovery/source-gem-contracts.md`.
2. **Ask UML for their own contract history**, and for three forwarded GeM alert emails while
   we are asking. The first answers ask 5 by the only free route and un-suppresses Module D;
   the second resolves assumption 3. One email, two unblocked assumptions.

   **Two more questions belong in the same email (added 2026-08-25), and one of them decides
   a purchase.**

   a. **Their ten category names exactly as GeM writes them** — a copy-paste from the seller
      dashboard, not a retyped list. `searchType=exact` is whole-field and case-sensitive, so
      five of their nine rope categories currently match nothing on the portal and the
      difference between a live category and a dead one is a capital letter (§Their ten
      categories). Costs them a screenshot; it is the difference between four categories of
      price history and ten.

   b. ~~**Which portals do they actually bid on besides GeM?**~~ **Answered on the buy side,
      2026-08-29 — and the question is now sharper, not closed.** The BidAssist feed was
      bought and probed: ten portals, **railways ahead of GeM**, 57% of rows from portals we
      do not touch (§the note under *What the portal will and will not give us*). So the
      buy/build answer has flipped — the feed is not redundant with the connector.
      What still needs UML's own voice is the **share**: a vendor's model of where a wire-rope
      seller sells is evidence, not a statement from the seller. Ask them to confirm the
      ranking, and specifically whether IREPS really is their biggest channel. If it is, an
      IREPS-shaped product is a different roadmap than a GeM-shaped one.

   > **Assumption 8 — resolved NEGATIVE, 2026-08-29.** *UML's tender pipeline is substantially
   > GeM.* It is not: the feed configured for this account is 46% Indian Railways and 43% GeM,
   > with eight other portals behind them. Written here when there was no evidence either way;
   > buying the feed produced the evidence, and it went the other way. The "~$83/mo, refuse on
   > redundancy" argument this note was hedging does not survive it.
3. ~~**Send the GeM SPV permission letter.**~~ **Closed 2026-08-25 — legal reviewed and
   cleared it.** It was never a blocker on any step here; a market-wide price feed was the only
   thing it could have unlocked, and steps 4 and 5 do not wait on it.
4. **One hour: does any other GeM surface publish award data without a captcha?** An open-data
   portal, a statistics dashboard, `data.gov.in`. §5 of the source review scopes it. Cheap, and
   it is the difference between "the portal refuses us" and "this endpoint refuses us".
5. **M11 — inbound email (revives M7).** Per-workspace address, GeM alert parse → normalised
   F-FR1 record, dedup against the crawled corpus, plus the clarification-request class. Answers
   ask 1's acquisition half and **all** of ask 4. **Blocked on step 2** — nobody has seen a GeM
   alert email, so its parse is unspecifiable (assumption 3).
6. ~~**M12 — routing.**~~ **Done 2026-08-14.** Owner + watch on every in-scope feed row; the
   engine refuses an assignee who is not a member of the workspace, because a tender routed to
   someone who cannot open it is the ask failing silently. A signed outbound webhook is still
   the CRM escape hatch, built when UML names their CRM.
7. ~~**Module H — product specs and catalogue fit.**~~ **Done 2026-08-14**, read-only, as
   specced: it gates nothing. Whether the *segment* is a product is still the commercial
   question — what shipped is the answer to asks 2 and 3, not a decision about assumption 7.

Steps 2–4 are asks and letters, not engineering, and they cost an afternoon between them.
Steps 5–6 are work already specced and already skipped once — they answer two and a half of the
five asks and need no new module. Step 7 is a commercial decision, not an engineering one.

**M13 (a contracts connector) is deleted, not deferred.** There is nothing to connect to.

## Deliberately not doing

- **Reading UML's GeM catalogue.** G-1, G-8, G-10. "Published" will mean *the catalogue you
  recorded with us*, never *GeM says so* — and it must say that on the screen, the way
  `coverage.py`'s docstring says `NOT_FOUND` is not non-compliance. A feature that silently
  implied a live GeM check would be worse than not having it.
- **Monitoring bid status on the portal.** Same reason, stated above. The email path is the
  answer to ask 4, not a workaround for it.
- **CRM integration**, until routing has been used and UML names the CRM. The ask names a
  solution; the sentence after it names the problem, and the problem is routing.
- **A wire-rope-specific schema.** Two of UML's ten categories (MIG welding wire) share almost
  no parameters with the other eight — the generic registry is required *within the first
  customer*, before the second one is even a question.
- **Auto-generating a GeM catalogue draft** from a `can be created` result. It is the obvious
  second slice and the real upsell; it ships after they trust the matching, not with it.
- **Wiring spec-fit into `recommend()`, the readiness hub, the lock gate or the export gate.**
  A brand-new comparator that can block an export before it has been seen on twenty real
  tenders is how a product starts refusing to work. Read-only screen in v1 — the same reasoning
  that kept the shredder out of the export gate (`docs/discovery/PRD.md` §11).

## Assumptions to veto

| # | Assumption | Confidence |
|---|---|---|
| 1 | ~~`/view_contracts` exposes per-**item** unit prices~~ | **Resolved NEGATIVE, 2026-08-07.** Moot — the search is CAPTCHA-gated and the endpoint is refused entirely (G-8) |
| 2 | UML's own contract history is complete enough, and granular enough (per item, not per PO), to price a schedule line | **Unverified, and this is now the gate on ask 5.** Ask before designing anything |
| 3 | GeM's seller alert emails carry enough structure to normalise into the F-FR1 record | Medium — the bid number is certainly present, which is the dedup key; the rest is unknown until we see one. **Ask UML to forward three.** |
| 4 | UML will maintain a manufacturing envelope by hand (≈5 envelopes, one sitting) | Medium-high — it is a one-time act by someone who knows the answer cold. If it is not maintained, every verdict decays to `unknown` and the feature reads as broken |
| 5 | UML's GeM catalogue can be exported and pasted or CSV'd | Medium — if not, v1 is envelope-only and every answer degrades from *Published* to *Can be created*, which is a materially weaker demo |
| 6 | Wire-rope parameters generalise across all ten of UML's categories | **Low.** MIG welding wire shares almost nothing with rope. Verify against two real tenders from different categories before sizing Module H |
| 7 | UML is a design partner, not a demo that gave feedback | **Unresolved, and it gates steps 5–6.** Steps 1–4 are worth doing regardless; Module H is not |
| 8 | UML's tender pipeline is substantially GeM rather than spread across CPPP, state and PSU portals | **Resolved NEGATIVE, 2026-08-29.** The BidAssist feed configured for this account carries ten portals, and **Indian Railways (ireps.gov.in, 46%) outranks GeM (43%)**; the remaining 11% is Telangana, AP, Haryana, SAIL, Coal India, Rajasthan ×2 and CPPP. Whoever configured that feed chose the portals a wire-rope seller sells through. Every estimate that treated GeM coverage as most of UML's coverage was wrong — including the redundancy argument against buying the feed. Worth confirming with UML directly, since this is a vendor's model of their market rather than UML's own statement |
| 10 | The BidAssist partner agreement permits showing this data to UML, who are not the licensee | **Unverified — nobody has read the contract**, and it is the riskiest open item on this page. GeM's §8 posture does not transfer: that is a copyright policy on a public site, this is a commercial licence |
| 11 | The vendor-side `FEED_SOURCE_ID` is a scope we can describe to a user | **Low.** All 120 sampled notices were wire rope, so the feed is already filtered by somebody who is not a user of this product — an exclusion with no author, which is what G-9 exists to forbid. Ask Nexizo whether the saved query can be read back |
| 9 | The category names UML sent are the strings GeM matches on | **Resolved NEGATIVE, 2026-08-25.** Five of nine matched no spelling tried; `exact` is whole-field and case-sensitive. Their own dashboard export is the fix, and it is asked for in step 2a |

Assumption 7 is the one to resolve first, and it is a conversation, not a spike. Assumption 8
is the same conversation and costs one more question in the same email.
