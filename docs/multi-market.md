# Serving a second market (France) — architecture decision

**Status:** proposed, 2026-07-31 · **Prompted by:** inbound interest from a French client
**Decision owner:** human sign-off required before any of §6 is built

## Decision

**One codebase with `market` as a first-class dimension. Not a fork, and not a second product.**

The instinct on hearing "another market" is to copy the repo and strip out the Indian parts. The
measurement below says that would duplicate the entire product in order to avoid changing about
twenty-three files, and would re-litigate the wall and guardrail discipline in two places
forever. Every future fix to the compliance matrix, the export gate, the audit trail or the
citation validator would have to be made twice, and the second copy would drift — that is not a
prediction, it is what happens.

## What is actually coupled to India

Measured on 2026-07-31, not estimated:

| Coupling | Files |
|---|---|
| Money and units (`formatINR`, `formatCrore`, `turnover_cr`, Lakh/Crore, ₹) | 14 |
| Indian statutory and policy vocabulary (EMD, ePBG, Udyam, DPIIT, MSE, MII, GST, PAN, CIN) | 9 |
| Hardcoded user-facing English strings in the app surface | ~86 |

Everything else is jurisdiction-neutral: the TOM and its lock gate, the compliance matrix and its
unmapped denominator, cite-or-flag, transclusion, the deterministic comparators, coverage counts,
export blockers, the approval chain, the audit trail, RLS and workspace isolation, and both
guardrail scripts. A tender is a tender; only the words and the money change.

Two structural facts make this easier than it sounds, and both were paid for already:

- **`opportunities` is already multi-source.** `source_id text not null` with
  `unique (source_id, portal_ref_no)` (migration 0019). The corpus was built for this.
- **The adapter contract already exists.** F-FR1's normalized record is what `gem-connector`
  emits and what `app/discovery/ingest.py` consumes. A second connector implements the same
  contract and nothing downstream changes.

## The three axes

Most internationalisation work fails by collapsing these into one "language" flag. They are
independent, and the product needs all three separately.

| Axis | Values | Governs | Lives on |
|---|---|---|---|
| **Locale** | `fr-FR`, `en-IN` | UI language, number/date/currency **format**, and the language the drafter writes in | user preference |
| **Market** | `FR`, `IN` | which sources are polled, which procurement vocabulary applies, which document parsers run, which thresholds | workspace |
| **Residency** | EU, IN | where the data physically lives | deployment |

They come apart in practice. A French client may want the UI in English. An Indian bidder may
legitimately pursue an EU tender — GeM's own listing carries `ba_is_global_tendering`, so this is
not hypothetical. And residency is a contractual question that has nothing to do with either.

## What is already true today

**The entire stack is EU-hosted.** Supabase is `eu-north-1` (Stockholm) and every Cloud Run
service except the GeM connector is `europe-north1`. The connector sits in `asia-south1` because
GeM is unreachable from Europe (`docs/discovery/known-pitfalls.md`), and it holds no tenant data.

The consequence is the opposite of what you would expect: **for a French client, GDPR residency
is already satisfied and needs no work.** The residency gap runs the other way — PRD §9 wants
Indian customer data in India and it is in Sweden. That is a pre-existing PH2 compliance item,
not a French blocker, and it should not be conflated with this work.

So: one codebase, **one deployment**, until a contract demands otherwise. When one does, it is
the same image against a second Supabase project in the required region — a move this repo has
already executed once, on the record, as "same image, two deploys, zero data movement".

## Discovery: France is the easier market, not the harder one

This is the part that looks like the blocker and is in fact the reward. The Indian source forced
every hard call in `docs/discovery/source-gem.md`: a session-gated JSON endpoint, an anonymous
WAF cookie that had to be argued against G-8, a `wkhtmltopdf` bid document reverse-engineered
label by label, and a copyright clause that forbids reproduction without written permission and
therefore shapes the entire UI toward facts-and-deep-links.

France has none of that.

- **BOAMP** (Bulletin officiel des annonces des marchés publics, run by DILA) publishes a free
  public API returning JSON, updated twice daily, seven days a week — and the data is released
  under **Licence Ouverte v2.0**, which grants reuse free of charge. That is a genuine T1 source
  in the PRD's own tiering, and it dissolves the §8 reproduction constraint that governs the
  Indian feed: French tender content may be stored and displayed, not merely linked.
- **TED** (Tenders Electronic Daily) covers EU-wide notices above threshold and publishes an
  official API. *Assumption — verify shape and rate limits at build time, per the discovery
  PRD's assumption register.*
- **CPV codes** are a proper controlled vocabulary. The rules engine's `category_prefix_in` /
  `category_prefix_not_in` were written against GeM's ad-hoc category strings; CPV is
  hierarchical and stable, so the same rule kinds get *better* on this market, not worse.
- **DUME / ESPD** is structured XML for the eligibility declaration. Where the Indian product
  parses a PDF form, the French one reads a schema.

The honest summary: the second market costs a connector and a vocabulary map, and it removes a
legal constraint rather than adding one.

## What changes, per axis

### Locale

- `apps/web/lib/format.ts` becomes locale-aware. `formatINR` and `formatCrore` collapse into
  `formatMoney(amount, currency, locale)`; `Intl.NumberFormat` already knows Indian grouping
  (`en-IN`) and French grouping (`fr-FR`, space separators and a comma decimal). This file is
  already the single chokepoint the conventions mandate — "never ad-hoc" — so the change is
  contained by design.
- A `[locale]` route segment plus a dictionary per locale. App Router needs **no new dependency**
  for this; resist adding one.
- **The drafter must write French.** This is the axis's real content, not the UI. A proposal
  drafted in English is unusable for a French bid, and it is the product's actual deliverable.

### Market

- `workspaces.market` and `opportunities.market`.
- The market sets a workspace's **default** corpus, never a hard filter. Hiding a cross-border
  tender a bidder could legally pursue would be an exclusion no user authored — F-AC6 in spirit,
  and ET-7 in consequence.
- A source registry keyed by market: `IN → gem_bidplus`; `FR → boamp, ted`. This is the
  `app/discovery/registry.py` the guardrail script already expects.
- A market-vocabulary module mapping **concepts, not words**: bid security (EMD ↔ *garantie de
  soumission*), performance guarantee (ePBG ↔ *garantie de bonne exécution*), small-enterprise
  status (MSE/Udyam/DPIIT ↔ *PME*), company identifiers (CIN/PAN/GST ↔ *SIREN/SIRET*). The
  comparators do not change — a turnover threshold is a turnover threshold. Only the labels and
  the parsers differ.

### Residency

Nothing now. When required: second deployment, second database, same image, `market` decides
which one a workspace lives in.

## Sequencing

The cheapest proof of the whole architecture is the one that touches no strings:

1. **`market` on workspace and corpus**, source registry keyed by it. No behaviour change.
2. **`boamp-connector`** — a new service emitting the existing F-FR1 record. Same Dockerfile
   shape, same guarded fetcher, same tests. Deployed in `europe-north1`, beside the data, because
   unlike GeM there is no reason to sit in another continent.
3. **Show a French tender ranked against a French capability statement, in the current English
   UI.** This validates the expensive claim — that a second market genuinely plugs in — before
   anyone touches 86 strings.
4. `format.ts` locale-awareness and the money-as-(amount, currency) change.
5. String extraction, `[locale]` routing, French dictionary.
6. **French prompts and French golden sets** — `evals/relevance-fr`, `evals/drafter-fr`. Per
   CLAUDE.md any `prompts/` diff requires an eval run, so this is the gate on whether the product
   can be sold in French at all, not a finishing touch.
7. Residency split, only when a contract demands it.

Steps 1–3 are the architecture. Steps 4–6 are the product. Step 7 is a contract.

## Deliberately not doing

- **Forking the repo.** See the measurement above.
- **Machine-translating the UI.** In a compliance product a mistranslated "mandatory",
  "self-attested" or "conditionally eligible" is a liability, not a typo. French strings are
  written or reviewed by someone who knows French public procurement.
- **Translating tender content.** The tender is the legal document; a translated requirement in a
  compliance matrix would be a claim about a text that does not exist. Show the source language,
  translate the interface around it.
- **A second `market` for the evaluate product** (`apps/evaluate`). Out of scope until asked, and
  the wall stays exactly where it is.

## Assumptions to veto

| # | Assumption | Confidence |
|---|---|---|
| 1 | BOAMP's API covers enough of the French market to be useful alone, without TED for above-threshold notices | Medium — measure coverage before committing to scope |
| 2 | CPV codes map cleanly onto the existing `category_prefix_*` rule kinds | Medium-high — CPV is hierarchical and prefix-shaped, which is the same shape GeM's codes have |
| 3 | Gemini drafts French of a quality a French bid manager will sign their name to | **Unverified, and this is the commercial gate.** Test before promising a French drafter to anyone |
| 4 | One deployment can serve both markets until a customer contract says otherwise | Medium-high — true today; a public-sector French buyer may still ask where the data sits |
| 5 | French clients want French UI rather than English | Low — ask the client. The axes are separate precisely so this can be answered late |
