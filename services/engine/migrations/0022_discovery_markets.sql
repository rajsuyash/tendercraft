-- Which countries a workspace WATCHES, as distinct from the one it IS registered in.
--
-- 0021 added `workspaces.market` and it quietly took on two jobs. One of them it does well:
-- a workspace has exactly one home country, and that is what decides its currency, which
-- statutory registers the profile asks for (GSTIN vs SIREN), the timezone a deadline means,
-- and the language our own stored explanations are written in. None of those can be a list —
-- a figure is either euros or rupees.
--
-- The other job it should never have had is deciding which corpora appear in the feed. That
-- one IS a list: GeM's own listings carry `ba_is_global_tendering`, a French consultancy may
-- legitimately want EU-wide notices, and a firm registered in one country bidding in another
-- is ordinary procurement, not an edge case. Conflating the two meant a bidder could only ever
-- see one country's tenders and had no way in the product to say otherwise.
--
-- So: `market` stays the home market and keeps every job above. `discovery_markets` is what
-- the feed reads.
--
-- This is also why the guardrail is satisfied. F-AC6 forbids the SYSTEM excluding a tender;
-- it does not forbid a bidder scoping their own feed. An unticked country is a named user
-- decision, visible on the profile page and stated on the feed's coverage strip — which is
-- exactly the attributability the rule exists to protect. What would violate it is what we
-- have today: a scope no user chose and no screen shows.
--
-- Additive and idempotent. The backfill is the point — a column only ONE code path writes
-- leaves every pre-existing row rendering as the fallback, which here would be an empty feed
-- for every existing workspace (docs/known-pitfalls.md names this trap by example).

alter table public.workspaces
  add column if not exists discovery_markets public.market[] not null default '{}';

-- Every existing workspace keeps exactly the feed it has today.
update public.workspaces
   set discovery_markets = array[market]::public.market[]
 where discovery_markets = '{}';

-- An empty array is not "no preference", it is "show me nothing", and nothing in the product
-- should be able to reach that state by accident: a silently empty feed is the ET-7 failure
-- (a tender never seen produces no error anywhere) wearing the friendly face of "no results
-- today". The constraint makes it unreachable rather than merely unlikely.
do $$ begin
  alter table public.workspaces
    add constraint workspace_watches_at_least_one_market
    check (cardinality(discovery_markets) > 0);
exception when duplicate_object then null; end $$;

comment on column public.workspaces.market is
  'Home market. Governs currency, statutory registers, timezone and the language of our own '
  'stored explanations. Exactly one — see discovery_markets for what the feed shows.';

comment on column public.workspaces.discovery_markets is
  'Which countries feed the opportunity list. User-chosen on /profile; defaults to {market}. '
  'Never empty (see constraint) — an empty feed must never be reachable by configuration.';
