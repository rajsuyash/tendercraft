-- Pursuits — the identity that survives the discovery/tender boundary.
--
-- `opportunities` (0019) is a SHARED corpus row: one per (source_id, portal_ref_no), visible to
-- every workspace whose market and rules reach it. `tenders` (0001) is workspace-private and
-- carries the bid. Nothing joined them. So a client who found a tender in the feed opened the
-- portal, downloaded the package, uploaded it back here, and re-typed the reference, the
-- authority and the deadline — on every pursuit, forever, with the discovery provenance
-- destroyed each time because there was nowhere to put it.
--
-- It also means no analytic about winning can exist. Selection performance, preventable-loss
-- analysis and discovery recall (F-AC1) all join on `surfaced -> pursued -> submitted ->
-- resolved`, and the first arrow did not exist. This table is that arrow.
--
-- WHY A TABLE AND NOT A COLUMN ON `tenders`. A nullable `opportunity_id` on `tenders` is the
-- smaller diff and the wrong shape: the pursuit begins BEFORE the tender exists — the user
-- claims it from the feed, then uploads the package, possibly days later, possibly never. A
-- lifecycle whose first state cannot be represented is one that gets reconstructed from guesses
-- later, and "never uploaded" is a real and interesting outcome we would lose entirely.
--
-- WHY NOT A COLUMN ON `opportunities`. That row is shared. Writing "workspace 7 is pursuing
-- this" onto it puts tenant-private intent into a corpus every other tenant reads. The wall
-- (F13) is about the two products, but the same reasoning governs the two scopes.
--
-- THIS TABLE GATES NOTHING. It records and links. No lock, no analysis, no export consults it.
-- Same reasoning that kept spec-fit read-only in v1: a brand-new object able to block an export
-- before it has been seen on twenty real tenders is how a product starts refusing to work.

do $$ begin
  create type public.pursuit_state as enum (
    'pursuing',   -- claimed from the feed; the package may not be uploaded yet
    'ingested',   -- a tender row exists and is linked
    'submitted',  -- the BIDDER says they submitted. We never read the portal (G-1/G-8)
    'abandoned'   -- decided not to bid. Kept, because why-we-did-not-bid is data
  );
exception when duplicate_object then null; end $$;

create table if not exists public.pursuits (
  id             uuid primary key default gen_random_uuid(),
  workspace_id   uuid not null references public.workspaces(id)    on delete cascade,

  -- `restrict` on both parents, deliberately, and this is a DEVIATION from the plan that
  -- specified `on delete set null` for tender_id. That pairing is broken: SET NULL fires, the
  -- `pursuits_ingested_has_a_tender` check below then fails, and the DELETE aborts with a
  -- check_violation naming a constraint on a table the deleter never mentioned. Restrict fails
  -- at the same moment for the same reason and says which table is holding the reference.
  --
  -- The consequence, stated rather than discovered: a pursued tender cannot be deleted while
  -- its pursuit exists. Nothing in the product deletes a tender today. Whoever adds that path
  -- decides then whether to detach the pursuit first (set tender_id null AND state back to
  -- 'pursuing', in one statement) or to refuse — and gets a clear error instead of a puzzle in
  -- the meantime. Same shape as the delete-workspace trap in docs/known-pitfalls.md.
  opportunity_id uuid not null references public.opportunities(id) on delete restrict,
  tender_id      uuid          references public.tenders(id)       on delete restrict,

  state          public.pursuit_state not null default 'pursuing',

  -- Bare uuids, matching 0027/0029/0038: no FK into the auth schema, which the ephemeral CI
  -- stack rebuilds from these migrations alone.
  owner          uuid,
  created_by     uuid,

  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  submitted_at   timestamptz,

  -- A state is a claim about something that happened; it needs the thing that happened.
  constraint pursuits_ingested_has_a_tender
    check (state <> 'ingested' or tender_id is not null),
  constraint pursuits_submitted_has_a_time
    check (state <> 'submitted' or submitted_at is not null),

  -- workspace_id INSIDE the key. The engine writes with the service role and bypasses RLS, so a
  -- conflict target omitting the scope column can reassign another workspace's row (0027).
  -- This is also what makes POST /pursue idempotent for free: a double-click is one pursuit.
  unique (workspace_id, opportunity_id)
);

-- 'submitted' is deliberately absent from the ingested check above. A bid that was submitted
-- stays submitted even if its tender row is later detached: the event happened, and a
-- constraint that quietly forbids recording history is worse than a nullable column.

create index if not exists pursuits_workspace_idx on public.pursuits(workspace_id, state);
create index if not exists pursuits_tender_idx    on public.pursuits(workspace_id, tender_id);

create or replace function public.pursuits_touch()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists pursuits_touch_trigger on public.pursuits;
create trigger pursuits_touch_trigger
  before update on public.pursuits
  for each row execute function public.pursuits_touch();

alter table public.pursuits enable row level security;

drop policy if exists pursuits_workspace_all on public.pursuits;
create policy pursuits_workspace_all on public.pursuits for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

comment on table public.pursuits is
  'The identity linking a shared-corpus opportunity to a workspace-private tender. Created when '
  'a user claims an opportunity from the feed, linked when the package is ingested, and the key '
  'every discovery-to-outcome analytic joins on. Gates nothing.';
