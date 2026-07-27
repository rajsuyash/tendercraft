-- Module G — the compliance matrix as a first-class artifact (tendercraft-discovery-PRD.md §6).
--
-- Until now the matrix existed only as a live assembly over proposal responses, rendered on
-- the export page. That serves the bidder who uses the Generator and gives nothing to the bid
-- manager who will draft in Word — which is most of them. These rows exist from the moment the
-- TOM locks, before any proposal.
--
-- Two tables, two different jobs:
--
--   matrix_rows      one row per criterion, carrying the HUMAN workflow (owner, status, where
--                    the response lives). Requirement text, level and anchor are copies of the
--                    locked TOM and are import-protected in code: a re-imported spreadsheet must
--                    never be able to rewrite a locked tender model without passing the lock gate.
--
--   matrix_unmapped  the denominator (G-FR2). Requirement-bearing sentences the shredder found
--                    that did NOT become a criterion. Without this, "we covered everything" is an
--                    assertion; with it, it is a measurement. Populated during ingest, while the
--                    page text is still in memory — this codebase does not persist tender text,
--                    so there is no second chance to compute it later.
--
-- Additive and idempotent. No existing column changes.

-- `create type if not exists` does not exist in Postgres; guard explicitly so the file stays
-- re-runnable.
do $$ begin
  create type public.matrix_row_status as enum (
    'not_started', 'drafting', 'drafted', 'reviewed', 'approved'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.matrix_unmapped_resolution as enum (
    'open',                -- still unresolved; blocks marking the matrix complete
    'not_a_requirement',   -- a human read it and said so. The audit trail keeps the claim.
    'mapped'               -- a human pointed it at a criterion
  );
exception when duplicate_object then null; end $$;

create table if not exists public.matrix_rows (
  id                uuid primary key default gen_random_uuid(),
  workspace_id      uuid not null references public.workspaces(id) on delete cascade,
  tender_id         uuid not null references public.tenders(id) on delete cascade,
  criterion_id      uuid not null references public.criteria(id) on delete cascade,
  -- Import-protected trio: copied from the locked TOM at generation, never writable by import.
  requirement_text  text not null,
  requirement_level public.requirement_level not null,
  anchor_page       int,
  anchor_clause     text,
  -- Human workflow: everything below is editable in-app and via XLSX round-trip.
  evidence_required text,
  response_ref      text,
  owner             uuid,
  status            public.matrix_row_status not null default 'not_started',
  due_date          date,
  notes             text,
  updated_at        timestamptz not null default now(),
  created_at        timestamptz not null default now(),
  -- One row per criterion per tender. workspace_id is IN the constraint deliberately: a
  -- service-role upsert whose on_conflict omits it can reassign another workspace's row
  -- (known-pitfalls, learned the hard way on this codebase).
  unique (workspace_id, tender_id, criterion_id)
);
create index if not exists matrix_rows_tender_idx    on public.matrix_rows(tender_id);
create index if not exists matrix_rows_workspace_idx on public.matrix_rows(workspace_id);

create table if not exists public.matrix_unmapped (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  tender_id    uuid not null references public.tenders(id) on delete cascade,
  sentence     text not null,
  page         int,
  resolution   public.matrix_unmapped_resolution not null default 'open',
  resolved_by  uuid,
  resolved_at  timestamptz,
  created_at   timestamptz not null default now(),
  -- Re-running ingest must not duplicate the backlog.
  unique (workspace_id, tender_id, page, sentence)
);
create index if not exists matrix_unmapped_tender_idx on public.matrix_unmapped(tender_id);
create index if not exists matrix_unmapped_open_idx
  on public.matrix_unmapped(tender_id) where resolution = 'open';

alter table public.matrix_rows     enable row level security;
alter table public.matrix_unmapped enable row level security;

drop policy if exists matrix_rows_workspace_all on public.matrix_rows;
create policy matrix_rows_workspace_all on public.matrix_rows for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

drop policy if exists matrix_unmapped_workspace_all on public.matrix_unmapped;
create policy matrix_unmapped_workspace_all on public.matrix_unmapped for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());
