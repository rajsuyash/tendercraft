# Source review — BidAssist partner API (Nexizo)

**Status:** built, **NOT enabled** · **Reviewed:** 2026-08-29 (engineering, agent-assisted live
probe) · **Human sign-off: REQUIRED and outstanding**
**Decision owner:** human. Two questions below are not engineering's to settle.

This is the third source review, after `source-gem.md` (T2, crawled, session-gated) and the TED
section of `docs/multi-market.md` (T1, open data). It is the first one where the data arrives
because a **contract** says it may, and that difference is the whole document.

## What arrived

An "API Access Details for DONNA AI LABS PRIVATE LIMITED" PDF from Nexizo: an `X-API-KEY`, two
POST endpoints under `https://partner-api.bidassist.in/api/public/v1`, and two feed identifiers.

| | |
|---|---|
| Vendor | BidAssist / Nexizo |
| Licensee | DONNA AI LABS PRIVATE LIMITED |
| Auth | `X-API-KEY` header, one key |
| Endpoints | `POST /tender/search`, `POST /tender-result/search` |
| Docs | `https://api-doc.bidassist.com/` — **403s to us**, so everything below was measured |
| Connector | `services/bidassist-connector` (`/health`, `/opportunities`, `/awards`) |
| Registry | `app/discovery/registry.py`, `source_id="bidassist"`, tier `T1-licensed`, **`terms_reviewed` blank** |

The key is in `.env` as `BIDASSIST_API_KEY` and named (never valued) in `.env.example`. The PDF
it arrived in sat untracked in the repo root; `/​*API*Access*` and `/​*.pdf` are now in
`.gitignore`, because `.env` being ignored does nothing when the same secret is also in a
document beside it and `git add -A` cannot tell them apart.

## The G-8 question — a proposed divergence, not a ruling

> **G-8 No authenticated acquisition.** Adapters never log in, never replay a session cookie,
> never store portal credentials, and never solve or bypass a CAPTCHA or bot check. A source
> that requires authentication is served by T3 (customer's own forwarded email) or not at all.

Read literally, an `X-API-KEY` header is a breach and this connector should not exist. The
argument that it is not:

- **G-8's subject is a portal** — a system whose operator did not agree to be read by us.
  Sending credentials there converts a public-page reader into a credentialed scraper and puts
  base PRD §9 ("no credentialed scraping in violation of portal terms") into the past tense.
  That is the act the rule forbids, and the reason it exists is F13: a government buyer has to
  be able to believe the evaluate product's separation claims, and "we scrape portals with
  borrowed logins" would end that conversation.
- **BidAssist is a licensed vendor.** It issued this key to us, for this use, under a paid
  agreement. Using it is not circumventing consent — it *is* the consent. The key is the same
  category of secret as `ANTHROPIC_API_KEY`, not the same category as a GeM seller login.
- **Nothing about the refusals in `docs/feedback/usha-martin.md` changes.** We still hold no
  customer credential and no portal credential. UML's GeM login stays untouchable (G-1). What
  changed is that a third party we pay is willing to hand over data it already collected.

**That reasoning is a proposal.** CLAUDE.md is explicit that reality contradicting the PRD gets
proposed to a human and logged, never silently drifted — and "we reasoned our way around a
guardrail" is exactly the failure mode the BOAMP refusal in `services/ted-connector/app/fetch.py`
was written to avoid. So the code exists and the source is **disabled**: its registry row carries
a blank `terms_reviewed`, and `for_market()` now enforces what that blank has always claimed to
mean. Enabling it is one line, by a human, after reading this.

**If it is ratified, the PRD text should change with it** — G-8 currently forbids a category of
act it did not mean to. Suggested amendment: *"never authenticate to a **portal**; a licensed
data vendor's own API key is permitted, and its licence terms are recorded in the source
registry."*

## The second question, which is sharper than the first

**`FEED_SOURCE_ID` is a saved query held on the vendor's side.** All 120 sampled notices were
about wire rope, without exception. Somebody has already decided what this feed contains, and it
was not a user of this product.

That is a filter we did not author, cannot inspect, and cannot enumerate — which is the exact
shape of the thing G-9 forbids, arriving from outside the system where G-9 cannot reach it. It
is not made safe by being upstream of us. A bidder shown an aggregator feed as if it were the
market concludes there are no tenders this month, and nothing anywhere produces an error (ET-7).

Handled three ways, none of which is a fix:

1. The sweep response carries `feed_source_id`, so corpus rows can be attributed to the saved
   query that produced them.
2. The registry entry records what the feed was observed to contain, and when.
3. This paragraph, and the requirement that **feed scope be re-verified whenever Nexizo changes
   it** — a change on their side is invisible on ours.

**What to ask Nexizo:** can the feed's query be read back through the API, or at least stated in
writing? A scope we can print beside the feed is a scope a user can disagree with. A scope we
cannot is an exclusion with no author.

## Reproduction terms — UNRESOLVED

`source-gem.md` §8 settled GeM: store and display **facts, not expression**; deep-link the prose.
That posture was recently reviewed and cleared by the owner's legal team.

**It does not transfer.** GeM's constraint is a copyright policy on a public website; BidAssist's
is a commercial contract nobody here has read. The partner agreement governs what may be stored,
displayed, and shown to a customer who is not the licensee — and the last question is the one
that matters, because this feed would be shown to UML.

Until the agreement is read, the connector's own posture is conservative by construction: it
emits facts (references, dates, values, portal host, bidder names and prices) and passes document
links through rather than copying document contents. **Test fixtures are synthetic for the same
reason** — the TED connector commits real captured notices because Licence Ouverte permits it;
nothing here reproduces vendor rows in the repo.

## What was measured, 2026-08-29

Live, against the real API. Every constant in the connector traces to a line here.

| Behaviour | Finding | Consequence in code |
|---|---|---|
| Page size | 20 works; 25/30/50/100 → `EIPS400 invalid page size or page number` | `PAGE_SIZE = 20`, a constant, not a tunable |
| Errors | **HTTP 200 with `{"data": null, "success": false, "errorCode": …}`** | the status line is not the answer — checked once in `fetch.search()`, never trusted to a call site |
| Success envelope | `{"data": [...], "last": bool}` — **no total count** | feed size can be measured, never read; `portal_total_ongoing` is null |
| Ordering | **none stable** across `dateModified`, `dateCreated`, `postingDate` | no incremental frontier and no cursor: sweep the whole feed |
| Feed depth | page 10 full, page 40 empty with `last=True`, both feeds | under 800 records ≈ 40 requests; a full sweep is cheap enough to be the only mode |
| Repeats | 100 fetched award rows → 96 distinct | offset paging over a shifting set; de-duplicated within a sweep |
| Unknown filter keys | `SEARCH`, `STATE`, an invented key → refused | good |
| **`KEYWORD`** | **accepted, and returned a page identical to the unfiltered control** | **the GeM `bidStatusType` trap again.** Only `FEED_SOURCE_ID` is sent; `build_body` is pinned by a test |
| robots.txt | 403 `Missing Authentication Token` (API gateway, no robots file) | treated as no rule; rate cap, byte cap and backoff apply regardless |
| Timestamps | epoch milliseconds throughout | converted to UTC ISO at the boundary; IST deadlines are display-time work |
| Document links | CloudFront presigned, `Expires` ≈ 7 days | URL emitted live; **signature stripped before hashing**, or `raw_snapshot_ref` would change every sweep for an unchanged tender |
| Value | `isTenderValueEstimated` marks vendor-inferred figures | inferred values never reach `estimated_value` — a value-band rule reads that field, so a guess there is a wrong exclusion |

## What the feed actually contains

120 notices sampled:

| Portal | Rows |
|---|---:|
| ireps.gov.in (Indian Railways) | 55 |
| bidplus.gem.gov.in | 52 |
| tender.telangana.gov.in | 4 |
| tender.apeprocurement.gov.in | 2 |
| etenders.hry.nic.in | 2 |
| sailtenders.co.in · coalindiatenders.nic.in · sppp.rajasthan.gov.in · eproc.rajasthan.gov.in · etenders.gov.in | 1 each |

Dates: posted 2026-06-15 → 2026-08-12, deadlines to 2026-09-25, 30 of 120 still `PUBLISHED`.

**Two things follow that are worth more than the connector.**

**Railways is bigger than GeM here.** `assumption 8` in `docs/feedback/usha-martin.md` — *is
UML's pipeline substantially GeM?* — has an answer, and it is no. Whoever configured this feed
chose the portals a wire-rope seller sells through, and GeM is 43% of them. Every estimate that
assumed GeM coverage was most of UML's coverage was wrong.

**Roughly half this feed duplicates `gem_bidplus`.** Those tenders will appear twice in the
corpus, under two `source_id`s. That is deliberate: the connector labels the overlap
(`source_fields.overlaps_source`) and merges nothing. A duplicate is visible and annoying; a
wrong merge is invisible and deletes a tender (F-AC4 = 0). Cross-source merge is a real feature,
it belongs in the engine, and it should be written against that field rather than a guess.

### The award ladder — and a correction

**BidAssist publishes L1..Ln, not just the winner.** Measured over 100 awards: 328 bidder rows,
55 awards with more than one bidder, 51 of those with an explicit `bidRank`, 44 with more than
one priced bidder, deepest ladder 12 bidders. An earlier read of this feed as single-awardee was
wrong, and it mattered — it was the argument for preferring the GeM connector's own award path.

Two fields are deliberately not invented, both for the reason the spec comparator gives:

- **`mse` is `None`, never `False`.** BidAssist publishes no MSE status. Rendering unknown as
  false states that a real company is not a small enterprise — a claim nobody made.
- **`rank` is `None` when the source omits it.** Sorting by price and calling the position a
  rank manufactures a ladder rung the portal never published. Unranked rows sort last, by price,
  and say so.

## Deliberately not doing

- **Enabling the source.** Blank `terms_reviewed`; `for_market()` refuses it. Two open questions
  above, both human.
- **Sending any filter but `FEED_SOURCE_ID`.** `KEYWORD` looks honoured and is not.
- **Merging BidAssist rows onto GeM rows.** Wrong altitude, and the destructive direction.
- **Wiring `/awards` into price history.** The endpoint exists and is proven; routing it into
  `deterministic/price_history.py` alongside the GeM ladder is a separate slice with its own
  question — the two sources disagree about MSE and about rank availability, and a price screen
  that silently blends them owes the user a note about which portal each rung came from.
- **Committing vendor rows as fixtures.** Terms unread.
- **Putting the key anywhere under `services/engine/app/discovery/`.** The guardrail script greps
  that tree unconditionally and must keep doing so; the credentialed source lives outside it,
  exactly as the GeM WAF cookie does.

## Assumptions to veto

| # | Assumption | Confidence |
|---|---|---|
| 1 | A licensed vendor API key is categorically unlike a portal credential, so G-8 does not forbid it | **Engineering's reading. Needs the decision owner.** The code is disabled until it has one |
| 2 | The partner agreement permits showing this data to UML, who are not the licensee | **Unverified — nobody has read the contract.** The riskiest open item here |
| 3 | The feed's scope is stable unless we ask for a change | **Low.** It is a setting on someone else's system with no change notification |
| 4 | Both feeds stay under ~800 records, so a full sweep remains the right mode | Medium — true on 2026-08-29; a widened feed would need a rethink, and there is no cursor to fall back on |
| 5 | `sourceTenderId` is unique within a portal | Medium-high — it is the portal's own reference, host-qualified before use; a collision would need the same portal to issue one number twice |
| 6 | Award coverage (~8 months observed) is deep enough for UML's five-year ask | **No.** Sampled `postingDate` runs 2025-12 → 2026-08. Ask 5 as worded is still unanswered by this source |
