-- The categories a seller is actually registered under on GeM (UML asks 1 and 5).
--
-- UML is registered under ten GeM product categories, nine of them rope against a named IS
-- standard. Those ten strings are the highest-value thing they told us, and until now the
-- product had nowhere to put them: a price-history fetch took a phrase somebody typed into a
-- box, and the feed matched keyword stems. Both re-derive, badly and every time, a fact the
-- customer already knows exactly.
--
-- **Why a category is a stored row rather than a search box.**
-- Measured on the live portal 2026-08-25: `/all-bids-data` accepts `param.searchType`, and
-- `exact` matches the WHOLE category field rather than OR-ing the query's words.
--
--     fullText  q='wire rope'        44,640 matching · 10 fetched · 0 survived relevance
--     exact     q='Steel Wire Rope'       6 matching ·  6 fetched · 6 survived, all with ladders
--
-- Same portal, same window, two requests per row either way. `exact` is not a nicer filter,
-- it is the difference between reaching a category's history and not: the sweep is
-- newest-first and capped, so under full text the budget is spent on rows that are then
-- discarded, and the older awards are never reached at all. That is the same failure the date
-- window was added to fix, one level up.
--
-- **`gem_name` is GeM's string, never the customer's.** `exact` is case-sensitive and whole-
-- field: 'Wire Rope' returns 6 awards, 'wire rope' returns 1, 'wire' and 'rope' return
-- nothing. Retyping a category from a customer's email produces a row that silently matches
-- zero awards and looks like a category with no history. So the name is HARVESTED from
-- `bd_category_name` on records the portal itself returned, and `verified_at` records when the
-- portal last confirmed it — a category that has never verified is not yet usable, and the
-- column says so instead of a comment somewhere hoping to be read.
--
-- **`standard_code` is separate from the name on purpose.** UML thinks in IS numbers (IS 2266,
-- IS 1855); GeM does not always write them into the category. Keeping the customer's language
-- beside the portal's is what lets a screen say "IS 2266 — General Engineering" over a row
-- whose portal name is something else entirely, without either string being corrupted into the
-- other. It is also the axis for the question nobody can answer today: which categories could
-- this seller register for that they have not.
--
-- Per-workspace and RLS'd, unlike `award_results` (0033) which is shared public market data.
-- A seller's registration list is their commercial position, not a public fact.

create table if not exists public.workspace_categories (
  id             uuid primary key default gen_random_uuid(),
  workspace_id   uuid not null references public.workspaces(id) on delete cascade,
  -- The portal's own string, exactly as GeM wrote it. This is the `searchType=exact` key.
  gem_name       text not null,
  -- The customer's words for the same thing, for screens and for their own recognition.
  label          text,
  -- 'IS 2266', 'API Spec 9A'. Nullable: MIG welding wire is registered against no standard.
  standard_code  text,
  -- When the portal last confirmed `gem_name` matches something. NULL = unverified, which is
  -- the honest state for a name that arrived from a spreadsheet and has never been tried.
  verified_at    timestamptz,
  -- What the portal said it holds for this category at that moment. Not a count of what we
  -- stored — the gap between the two is what stops a 6-row sample being read as the market.
  portal_award_total int,
  -- Off means "keep the row, stop sweeping it". Deleting would lose the verification.
  active         boolean not null default true,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  -- workspace_id inside the key for the 0027 reason: the engine writes with the service role
  -- and bypasses RLS, so a conflict target without the scope column can overwrite another
  -- workspace's row (docs/known-pitfalls.md).
  unique (workspace_id, gem_name)
);

create index if not exists workspace_categories_ws_idx
  on public.workspace_categories(workspace_id) where active;

alter table public.workspace_categories enable row level security;

drop policy if exists workspace_categories_workspace_all on public.workspace_categories;
create policy workspace_categories_workspace_all on public.workspace_categories for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

comment on column public.workspace_categories.gem_name is
  'GeM''s own category string, harvested from a portal record — never retyped. searchType='
  '''exact'' is whole-field and case-sensitive, so an invented spelling matches nothing and '
  'presents as a category with no award history rather than as an error.';

comment on column public.workspace_categories.verified_at is
  'NULL means the portal has never confirmed this name. Unverified rows are stored and shown, '
  'never swept: a fetch against an unmatched name burns portal budget to return zero.';
