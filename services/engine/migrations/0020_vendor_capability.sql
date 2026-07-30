-- Vendor capability → the relevance signal (F-FR11, tendercraft-discovery-PRD.md §3.3).
--
-- The audit of the in-scope feed found that "in scope" meant "no user rule fired", not
-- "relevant": nothing in the system knew what the workspace sold, so an IT-services vendor was
-- shown hypodermic syringes, modular toilets and adhesive gum. These two columns are what the
-- product learns about the vendor; everything downstream ranks against them.
--
-- Additive and idempotent. No existing column changes, and vendor_profiles' RLS policy is
-- row-level with no column list (0002:55, renamed at 0010:68), so new columns are covered with
-- no policy change.

alter table public.vendor_profiles
  -- Free prose. Feeds the model relevance band, and is deliberately unstructured because the
  -- thing a bidder can say about their own capability does not fit a taxonomy.
  add column if not exists capability_statement text,
  -- `not null default '{}'` matches every other text[] in this schema (profile_financials'
  -- scope_tags at 0002:31, opportunities.category_codes at 0019:52). A nullable array hands
  -- every consumer a None to iterate over, and the first one to forget a guard raises TypeError
  -- inside a request rather than at the boundary.
  add column if not exists capability_keywords text[] not null default '{}';

-- The band is an ENUM, not text, and the member order is load-bearing: Postgres sorts an enum
-- by declaration order, so `order by relevance_band` yields high → medium → low. As text it
-- sorted ALPHABETICALLY — high, low, medium — which silently puts the worst matches second and
-- looks like a ranking that simply does not work.
do $$ begin
  create type public.relevance_band as enum ('high', 'medium', 'low');
exception when duplicate_object then null; end $$;

-- Safe to convert: 0019 shipped the column as text and nothing has written to it yet.
alter table public.opportunity_matches
  alter column relevance_band type public.relevance_band
  using nullif(relevance_band, '')::public.relevance_band;

alter table public.opportunity_matches
  -- The cited evidence for the band, in words: the matched keywords, or the model's matched
  -- capability. F-FR11 requires the signal to carry what matched — a band on its own is an
  -- opinion, a band with its evidence is a claim the user can check.
  add column if not exists relevance_reason text,
  -- 'model' | 'keyword' | null. Recorded so a model outage is VISIBLE rather than silent: the
  -- feed degrades to deterministic keyword banding and says so, instead of quietly changing
  -- what "high" means (EC-6's honesty rule applied to ranking).
  add column if not exists relevance_source text,
  add column if not exists relevance_scored_at timestamptz,
  -- Cost control. Hash of (capability statement + keywords + this tender's title/categories);
  -- an unchanged hash means the answer cannot have changed, so the model is not called again.
  -- Without this, every rule edit would re-score the whole feed (PRD §4.1).
  add column if not exists relevance_input_hash text;

-- Ordering the feed reads band first, so it needs an index that matches.
create index if not exists opportunity_matches_ws_band_idx
  on public.opportunity_matches(workspace_id, state, relevance_band);
