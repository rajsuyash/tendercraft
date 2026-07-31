-- Second market (France) — the three axes made explicit (docs/multi-market.md).
--
-- The doc's whole argument is that locale, market and residency are independent, and that
-- collapsing them into one "language" flag is how internationalisation work goes wrong. This
-- migration is that argument in DDL: three columns, on three different tables, because they
-- belong to three different owners.
--
--   workspaces.market            which sources feed this workspace, which vocabulary applies
--   profiles.locale              ONE USER's interface preference — not the workspace's
--   opportunities.notice_language what language the tender itself is written in
--
-- Additive and idempotent. Existing rows backfill to the market they were always in.

do $$ begin
  -- No natural ordering, unlike relevance_band — an enum here is for validity, not for sort.
  create type public.market as enum ('IN', 'FR');
exception when duplicate_object then null; end $$;

alter table public.workspaces
  add column if not exists market public.market not null default 'IN';

-- A user's interface language. On `profiles` and NOT on `workspaces` deliberately: two people
-- in the same French workspace may want different interfaces, and neither choice may change a
-- single character of what a tender says.
alter table public.profiles
  add column if not exists locale text not null default 'en';

alter table public.opportunities
  add column if not exists market public.market not null default 'IN',
  -- The language the NOTICE is written in, as declared by the source — BOAMP's eForms payload
  -- carries `cbc:NoticeLanguageCode` (FRA), so this is read, never inferred. It decides what
  -- language the drafter must WRITE, which is a property of the tender and not of the reader:
  -- a French buyer receives a French bid however the bid manager set their toggle. TED carries
  -- multilingual notices, so inferring this from `market` would be wrong there.
  add column if not exists notice_language text;

-- Backfill: everything swept so far is GeM, which is Indian and English-language.
update public.opportunities
   set market = 'IN', notice_language = coalesce(notice_language, 'en')
 where source_id = 'gem_bidplus';

create index if not exists opportunities_market_idx on public.opportunities(market, closing_at);
