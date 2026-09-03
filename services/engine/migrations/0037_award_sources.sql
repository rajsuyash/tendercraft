-- The award corpus stops being GeM-shaped (UML ask 5, second source).
--
-- Migration 0033 built `award_results`/`award_prices` around one portal, and three of its
-- columns encode assumptions that are true of GeM and false of a licensed aggregator. Wiring
-- a second source in without this migration would not fail — it would silently write claims
-- nobody published, which is the failure this schema exists to prevent.
--
--   `mse not null default false`  GeM publishes MSE status; BidAssist does not publish it at
--                                 all. Defaulting to false states that a named real company
--                                 is NOT a small enterprise — a claim about a third party
--                                 that no source made. NULL means not published, exactly as
--                                 an unrecorded spec parameter reads NOT ASSESSED rather
--                                 than `deviation`.
--   `rank not null`               Measured on 100 BidAssist awards (2026-08-29): 55 carry
--                                 more than one bidder and only 51 of those carry an explicit
--                                 `bidRank`. Sorting the rest by price and calling the result
--                                 a rank manufactures a ladder position the portal never
--                                 published. NULL rank + `awarded` is what the source
--                                 actually says.
--   `bid_end_date`                GeM publishes when bidding CLOSED; BidAssist publishes when
--                                 the contract was AWARDED. They are weeks apart and they are
--                                 not the same event, so the second one gets its own column
--                                 rather than being written into the first. `observed_date`
--                                 is the sortable axis both share, generated rather than
--                                 written so the two can never drift.
--
-- `unique (award_result_id, rank)` survives unchanged and stays useful: Postgres treats NULLs
-- as distinct, so it still forbids two L1s while allowing many unranked bidders.

alter table public.award_prices alter column mse  drop not null;
alter table public.award_prices alter column mse  drop default;
alter table public.award_prices alter column rank drop not null;

-- Who the source says won, for the ladders that carry no rank. Backfilled from the rank that
-- already exists rather than left false: every stored row today is GeM, where rank 1 IS the
-- award, and a column only the new path writes would report the whole existing corpus as
-- having no winner (docs/known-pitfalls.md, `proposal_sections.original_md`).
alter table public.award_prices add column if not exists awarded boolean not null default false;
update public.award_prices set awarded = true where rank = 1 and awarded = false;

alter table public.award_results add column if not exists award_date timestamptz;
alter table public.award_results add column if not exists observed_date timestamptz
  generated always as (coalesce(bid_end_date, award_date)) stored;

create index if not exists award_results_observed_idx
  on public.award_results(observed_date desc);

comment on column public.award_prices.mse is
  'Small-enterprise status AS PUBLISHED. NULL means the source does not publish it (BidAssist '
  'does not); false means the source published that this seller is not an MSE. Never coalesce '
  'the two — one is a fact about a company, the other is a fact about a feed.';

comment on column public.award_prices.awarded is
  'The source named this bidder the winner. Carried separately from rank because an aggregated '
  'feed often publishes who won without publishing the ladder position.';

comment on column public.award_results.observed_date is
  'The one date every source has: bid close where published (GeM), contract award otherwise '
  '(BidAssist). Generated, so ordering and the five-year window cannot drift from the columns.';
