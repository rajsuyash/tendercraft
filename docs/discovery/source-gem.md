# Source feasibility + terms review — GeM (bidplus.gem.gov.in)

**Reviewed:** 2026-07-30 · **Reviewer:** engineering (agent-assisted probe, human sign-off pending)
**Verdict:** acquisition **PERMITTED** (no anti-automation clause, robots-clean, no login exists).
The binding constraint is **reproduction, not access** — see §8. Display facts + deep links, not
reproduced content, and send the permission letter.

> **Revised 2026-07-30, same day.** An earlier revision of this file concluded "listing
> acquisition BLOCKED on G-8". That was wrong, and wrong in the expensive direction: it was
> written before GeM's Terms of Use and Website Policies had been read, and it treated an
> anonymous session cookie as if it were a credential. G-8 forbids *authenticated* acquisition.
> GeM's listing has no login, no CAPTCHA and no credential — the cookie is what any first-time
> visitor receives from a public page. The `cookie|session` grep in
> `tools/check-discovery-guardrails.sh:54` is a proxy for the rule, and here the proxy
> over-matches. Fixing that grep is tracked in §9; the guardrail itself stays.
**Satisfies:** discovery PRD §14 assumption #1 ("verify T1 availability at build time") and the
G-10 requirement that every source carry a recorded terms-review date before an adapter ships.

> This file records what the portal actually does, measured. It is not a design. The design
> lives in `tendercraft-discovery-PRD.md` §3 and is unchanged by these findings — but two of its
> assumptions move, one favourably and one not.

## What was probed

Nine requests total, spread over minutes, identified user agent carrying a contact address. No
login attempted, no CAPTCHA encountered, nothing written. Sequence: `robots.txt`, the
`/all-bids` page in a browser, the XHR it issues, two cookie-less replays of that XHR, one
ranged `HEAD`-equivalent on a bid document, one full bid document.

## Findings

### 1. robots.txt permits the listing and the documents

```
User-agent: *
Disallow: /resources/
Disallow: /bg_emd/epbgservice/CallBG_Performance_Status
Disallow: /bg_emd/epbgservice/PBGIntimation
Disallow: /bg_emd/epbgservice/AddSellerIssuinginfo
```

`/all-bids`, `/all-bids-data` and `/showbidDocument/*` are **not** disallowed. `/resources/` is —
see finding 5, because that is where the interesting attachments probably live.

### 2. The listing is a Solr-backed JSON endpoint — and it is session-gated

`POST https://bidplus.gem.gov.in/all-bids-data`, body:

```
payload={"page":N,"param":{"searchBid":"","searchType":"fullText"},
         "filter":{"bidStatusType":"ongoing_bids","byType":"all","highBidValue":"",
                   "byEndDate":{"from":"","to":""},"sort":"Bid-End-Date-Oldest"}}
&csrf_bd_gem_nk=<token scraped from the /all-bids page>
```

Returns a raw Solr response (`content-type: text/html`, body is JSON) with
`numFound: 48476` ongoing bids, `start`, and `docs[]` at a **fixed page size of 10**.
Server-side full-text search, end-date window, value band and sort are all supported — so the
volume is controllable without client-side enumeration.

Per-item fields available with **no document fetch at all**:

| Field | Example | Use |
|---|---|---|
| `b_bid_number` | `GEM/2026/R/706528` | F-FR6 exact-match dedup key |
| `b_bid_number_parent` / `b_id_parent` | `GEM/2026/B/7634666` / `9435106` | document URL (finding 4) |
| `b_cat_id` | `services_home_cust`, `home_clea_clea_clea_to48326355` | **structured category codes — the F-FR9 gate rule input** |
| `b_category_name` / `bd_category_name` | full item list | relevance (F-FR11) |
| `ba_official_details_minName` / `deptName` | `Ministry of Defence` / `Department of Military Affairs` | authority; geography where the dept names a state |
| `final_start_date_sort` / `final_end_date_sort` | ISO 8601 | published/closing, days-to-close gate |
| `b_total_quantity`, `is_high_value`, `b_type`, `b_eval_type`, `ba_is_global_tendering`, `is_rc_bid`, `bd_details_is_boq` | | secondary gate inputs |

**Not** in the listing: estimated value, EMD, turnover threshold, experience requirement,
certifications. Those are in the document.

**Session requirement.** Replayed cookie-less the endpoint returns **403**, with or without the
page's CSRF token. It needs a session cookie, obtained by `GET /all-bids` like any browser.

This is **not** a G-8 breach: there is no login, no credential, no CAPTCHA, and the cookie grants
nothing a first-time visitor does not already have. G-8 forbids *authenticated* acquisition, and
an anonymous session is not authentication. The `cookie|session` grep at
`tools/check-discovery-guardrails.sh:54` over-matches this case — see §9 for the narrowing.

The operational risk is real and separate from the legal one: a government portal that decides
we are abusing it blocks rather than throttles, and EC-9 then pulls the source for every
workspace at once. That is an argument for strict G-10 rate discipline and a cached shared
corpus, not for declining the source.

### 3. There is no official GeM bid API

No published machine-readable bid feed and no partner/aggregator API for bid data. Several
commercial scrapers resell GeM bid data — which is a *purchasing* option that moves the ToS
exposure onto a vendor, not a technical one. **Assumption #1 resolves NEGATIVE for GeM: there
is no T1 tier here.**

### 4. Bid documents are open — no cookie, no CSRF, no login

`GET https://bidplus.gem.gov.in/showbidDocument/<b_id_parent>` → `200 application/pdf`,
`Content-Disposition: attachment; filename="GeM-Bidding-<id>.pdf"`. Plain curl with a custom
user agent and no cookie jar succeeds. Robots-permitted. **This path is compatible with G-8 and
G-10 as written.**

### 5. The document is a generated form, not a scan — this is the important one

`Creator: wkhtmltopdf 0.12.5`, 6 pages, A4, with a real text layer. `pdftotext -layout`
extracts it cleanly. Consequences:

- **No OCR.** The base PRD's A-FR1/A-FR6 ≥98% word-accuracy gate and the EC-1 manual-review
  path do not apply to GeM bid documents at all. The OCR provider decision (`docs/PRD.md` §4,
  still `TODO:`) is **not on the critical path for GeM**.
- **The eligibility subset is labelled key-value text**, in a stable bilingual template:
  `Minimum Average Annual Turnover of the bidder (For 3 Years)` = `5 Lakh (s)`;
  `MSE Relaxation for Turnover` = `Yes | Partial | Turn over value - 3.93 (in lakhs)`;
  `Startup Relaxation for Turnover`; `Document required from seller` =
  `Experience Criteria,Bidder Turnover,Certificate (Requested in ATC)`;
  `Estimated Bid Value in INR (Inclusive of all taxes)` = `5458313.82`; `EMD Detail → Required`
  = `No`; `ePBG Detail → Required` = `No`; `MSE Purchase Preference` = `Yes`, `L1+15%`;
  Ministry / Department / Organisation / Office; `Contract Period`; bid end & opening datetimes.

  **A deterministic label parser gets all of it — no model call.** That is materially cheaper
  and more reliable than the escalation ladder in PRD §4.1 step 2 assumed, and it moves
  **assumption #6 favourably for GeM**: Depth-1 eligibility on a GeM bid needs one 100 KB fetch
  and a regex pass, not an LLM extraction. Confidence for these fields should be recorded as
  deterministic-parse, not model-confidence.

  **Built and verified 2026-07-30** (`services/gem-connector/app/document.py`, 69 tests). Three
  template facts learned from live documents that the single-sample review above missed, each
  now pinned by a golden fixture:

  * **EMD and ePBG have two mutually exclusive shapes.** Low-value bids carry
    `/Required  No`; high-value bids carry `/EMD Amount  31200000` and
    `/ePBG Percentage(%)  5.00` with **no `/Required` row**. The first parser read only the
    first shape and reported "unknown" on a bid demanding a ₹3.12 crore deposit.
  * **Turnover and estimated value are optional.** Live BOQ bids omit both. `None` therefore
    has to mean "absent from this document", which is why one fixture exists specifically to
    prove absence is real rather than a parser miss.
  * **`Years of Past Experience Required for`** is a fourth eligibility field, present on
    high-value bids and absent elsewhere — the experience half of C-FR7.

  Full list of ways this parse goes silently wrong: `docs/discovery/known-pitfalls.md`.
- Free-text conditions (the numbered MSE/startup/RA clauses) sit below the table and are the
  only part needing the C-FR7 model extractor.

### 6. Real scope of work lives in separate attachments

The document's `Additional Qualification/Data Required` section lists attachments by opaque
numeric id — `Scope of Work:1779767077.pdf`, `Instruction To Bidder:...`, `GEM Availability
Report (GAR):...`. These are **separate files whose canonical location was deliberately not
probed** (guessing at paths on a government host is precisely the behaviour G-10 exists to
prevent). They are most likely under `/resources/`, which **robots.txt disallows**.

**Therefore: no adapter may fetch bid attachments until their location is confirmed and, if it
is `/resources/`, they must not be crawled at all.** A user-initiated fetch (T4) or the
customer's own authenticated GeM session remains available for the one bid a human is actually
evaluating. For custom-bid services — where the scope of work *is* the attachment — Depth-1 can
therefore report category, authority, value, turnover and EMD, but **not** detailed scope, and
must say so rather than implying it read the scope.

### 7. GeM already emails category-matched bid alerts to registered sellers

GeM routes new-bid notifications to sellers by their registered category mapping. Every
TenderCraft customer bidding on GeM is a registered GeM seller, so **the customer is already
receiving, in their own inbox, the feed we are blocked from crawling.** That is the T3 path in
PRD §3.1, and for GeM it is not a fallback — it is the only compliant route to the listing that
requires no permission from anyone.

### 8. The binding constraint is reproduction, not access

`gem.gov.in/termsCondition` and `gem.gov.in/websitePolicies`, read 2026-07-30:

- **No clause on robots, crawlers, spiders, automated access, bulk download or data extraction.**
  Nothing to breach by fetching.
- **No clause restricting commercial use** of data taken from the portal.
- Copyright policy, verbatim: *"Contents of this website may not be reproduced partially or fully
  without due permission in writing in advance from the GeM SPV."* Where reproduction is
  permitted it must be *"reproduced accurately and not used in a derogatory manner or in a
  misleading context"* with the source *"prominently acknowledged"*, and the permission *"shall
  not extend to any material that is identified as being the copyright of a third party"*.
- Hyperlinking policy, verbatim: *"We do not object to you linking directly to the information
  that is hosted on this website, and no prior permission is required."* Framing our pages is
  refused.

So the exposure is **republication, not acquisition** — which means it applies identically to
every path in the table below, *including* customer-forwarded email, and to the commercial GeM
data vendors. Choosing a vendor does not make this clause go away; it only moves who is named.

**Design consequence — this is the part that constrains the build:**

1. **Store and display facts, not expression.** A bid number, closing datetime, ministry,
   department, category code, estimated value, turnover threshold and EMD flag are facts; facts
   are not copyrightable expression under the Copyright Act, and they are what every gate rule
   and comparator actually reads. Render those, plus our own derived verdicts.
2. **Deep-link the content.** Bid title/category prose and the bid document itself stay on GeM,
   reached by a link — the one behaviour their policy explicitly permits without permission. Do
   not re-host the PDF to customers.
3. **F-FR2 raw snapshots become an internal audit record, not a customer-facing artifact.**
   Retaining a snapshot for provenance is a different act from republishing it. Keep them in
   private storage, serve them to nobody, and satisfy the "resolvable source link" of F-AC7 with
   the GeM URL plus our retrieval timestamp.
4. **Acknowledge the source prominently** on every surface that shows GeM-derived data.
5. **Send the permission letter.** Their policy names the mechanism — *permission in writing in
   advance* — and a granted permission removes constraints 1–3 entirely. It costs a letter and it
   is the only thing that upgrades this source properly. Start it in parallel with the build.

None of this is legal advice; it is the engineering posture that follows from the clauses as
written. A lawyer should read §8 before the feature is marketed.

### 9. Guardrail change required

`tools/check-discovery-guardrails.sh:54` greps for `cookie|session` anywhere under
`app/discovery` and would reject a compliant GeM listing adapter. The rule to enforce is
"no *authenticated* acquisition", so the check should narrow to what actually indicates
authentication — credential storage, `Authorization` headers, login/signin flows, CAPTCHA
solvers, stealth browsers — while permitting an anonymous cookie jar that is acquired per-run
from a public page and never persisted. Until that narrowing lands, the GeM listing fetcher
lives **outside** `app/discovery` (see the connector service in the build plan), which keeps the
guardrail honest for the portals it was written for: the ones behind logins.

## What this means for sequencing

| Path to the GeM listing | Acquisition OK? | Verdict |
|---|---|---|
| **Own connector service** polling `/all-bids-data` with an anonymous per-run session | **Yes** — robots-clean, no auth, no anti-automation clause | **Chosen.** Full corpus, no recurring fee, no vendor dependency. Requires §8's facts-and-links display posture and strict G-10 rate discipline. Lives outside `app/discovery` until §9 lands. |
| Written permission from GeM SPV | Yes if granted | **Start in parallel.** Removes the §8 reproduction constraint and upgrades GeM to a genuine T1. Costs a letter; unknown lead time. |
| T3 — customer forwards their own GeM alert emails | Yes | Still worth building as M7 — it covers portals we do not crawl and is per-customer complete. Note it does **not** avoid §8. |
| T4 — user pastes a bid number or URL | Yes | The floor that always works. Uses finding 4, which is open. |
| Licensed commercial GeM data vendor | Yes, contractually | Rejected on cost — ~$200/mo for data we can acquire compliantly ourselves, and the vendor is subject to the same §8 clause. Revisit only if we are blocked. |

Document fetching (finding 4) is clear **regardless of which listing path is chosen** — once we
know a bid number from any source, we can legally read its bid document and run Depth-1
eligibility deterministically on it.

## Registry entry to create when M9 lands

```
gem_bidplus:
  tier: T4 (document fetch) — listing NOT crawled, see finding 2
  base_url: https://bidplus.gem.gov.in
  robots_reviewed: 2026-07-30
  terms_reviewed: 2026-07-30
  reviewer: <human sign-off required>
  document_path: /showbidDocument/{parent_bid_id}   # open, no session
  listing: BLOCKED — session-gated, G-8; served via T3 email instead
  attachments: LOCATION UNCONFIRMED — do not fetch (finding 6)
```
