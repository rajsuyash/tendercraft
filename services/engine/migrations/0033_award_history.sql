-- What GeM bids actually closed at (UML ask 5) — the shared public corpus.
--
-- No workspace_id, on purpose, for exactly the reasons migration 0019 gives for
-- `opportunities`: these are public award records, identical for every customer. Copying them
-- per tenant would multiply the row count by the customer count and re-crawl the same pages
-- once per workspace, to store the same facts.
--
-- Read by any authenticated user; written by NOBODY through the API. The absence of an
-- INSERT/UPDATE/DELETE policy is the write protection — only the service-role connector
-- ingest can populate this, so a customer cannot edit market history into a shape that suits
-- their bid.
--
-- **What is stored, and why it is allowed.** GeM's copyright policy forbids reproducing site
-- contents. A price, a rank, a seller name, a quantity and a date are FACTS; the prose is not
-- stored, and `source_url` deep-links back to the page. That is the posture
-- docs/discovery/source-gem.md §8 already settled for the listing, applied unchanged.
--
-- **The one number that is deliberately NOT here: unit price.** `total_price` is what the
-- seller bid for the whole schedule, and GeM bundles unrelated items into one bid
-- ("Wire Copper Insulated, Fevi Quick, Throttle Spray, ..."). Dividing by quantity across a
-- bundle produces a per-unit figure that is confidently wrong, and a wrong benchmark price is
-- worse than none — it is the number someone would price a real bid against. The engine
-- derives an implied rate only where the bid is for a single category, and says which it is.

create table if not exists public.award_results (
  id             uuid primary key default gen_random_uuid(),
  source_id      text not null default 'gem_bidplus',
  -- The dedup key, normalized exactly like opportunities.portal_ref_no (F-FR6).
  portal_ref_no  text not null,
  category       text,
  department     text,
  quantity       numeric,
  bid_end_date   timestamptz,
  -- 'tech_evaluated' | 'fin_evaluated' | 'bid_awarded'. A result page exists before the award,
  -- and a ladder read at financial-evaluation stage is real but not yet final.
  stage          text not null default 'bid_awarded',
  participants   int not null default 0,
  source_url     text,
  fetched_at     timestamptz not null default now(),
  unique (source_id, portal_ref_no)
);
create index if not exists award_results_category_idx on public.award_results
  using gin (to_tsvector('simple', coalesce(category, '')));
create index if not exists award_results_date_idx on public.award_results(bid_end_date desc);

create table if not exists public.award_prices (
  id                uuid primary key default gen_random_uuid(),
  award_result_id   uuid not null references public.award_results(id) on delete cascade,
  seller            text not null,
  mse               boolean not null default false,
  total_price       numeric not null,
  -- 1 is L1, the winner. The whole ladder is kept, not just the winner: "what did the runner-up
  -- bid" is the question that tells a bidder how much room they had, and it is free to store.
  rank              int not null,
  offered_item      text,
  unique (award_result_id, rank)
);
create index if not exists award_prices_result_idx on public.award_prices(award_result_id);

alter table public.award_results enable row level security;
alter table public.award_prices  enable row level security;

-- Read-only to every authenticated user; no write policy anywhere, which IS the protection.
drop policy if exists award_results_read_all on public.award_results;
create policy award_results_read_all on public.award_results for select
  using (auth.role() = 'authenticated');

drop policy if exists award_prices_read_all on public.award_prices;
create policy award_prices_read_all on public.award_prices for select
  using (auth.role() = 'authenticated');

comment on column public.award_prices.total_price is
  'What this seller bid for the WHOLE schedule, as published. Not a unit rate: GeM bundles '
  'unrelated items into one bid, so dividing by quantity is confidently wrong more often than '
  'it is right, and a wrong benchmark is worse than none.';

comment on table public.award_results is
  'Public GeM award facts. Shared corpus (no workspace_id) for the same reasons as '
  'opportunities; read-only through the API, written only by the service-role ingest.';
