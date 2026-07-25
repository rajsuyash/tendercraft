-- Projects: a pursuit within a workspace.
--
-- Buys exactly three things, all real:
--   1. a pursuit is a unit — one bid can span several related tenders/lots
--   2. it has an owner
--   3. it has a won/lost lifecycle that has nowhere to live today: tender_status stops at
--      'locked' and proposal_status stops at 'exported', so whether the firm actually WON
--      is unrepresentable except in `outcomes`, which is a statistics corpus not a workflow.
--
-- Only `tenders` gets project_id. Everything else reaches a project THROUGH the tender;
-- adding the column elsewhere is denormalization with no query behind it and another
-- unique-key/on_conflict landmine.
--
-- Deliberately NOT built: project members (the workspace is the membership boundary — a
-- second one inside it is the same trap), project-level RBAC, templates, nested projects,
-- saved views. Each is a guess about a workflow no customer has described.
-- Idempotent.

create table if not exists public.projects (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  name         text not null,
  status       text not null default 'active',   -- active | won | lost | archived
  owner        uuid,                             -- profiles.user_id
  created_at   timestamptz not null default now(),
  unique (workspace_id, name)
);
create index if not exists projects_workspace_idx on public.projects(workspace_id);

alter table public.tenders add column if not exists project_id uuid
  references public.projects(id) on delete set null;
create index if not exists tenders_project_idx on public.tenders(project_id);

-- Keyset pagination index. Projects group lists; they do NOT make row 51 reachable —
-- only a cursor does, and known-pitfalls.md has named this since M0.
create index if not exists tenders_ws_created_idx
  on public.tenders (workspace_id, created_at desc, id desc);

alter table public.projects enable row level security;

drop policy if exists projects_workspace_all on public.projects;
create policy projects_workspace_all on public.projects for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());
