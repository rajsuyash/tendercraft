-- Organizations + workspace membership. The enterprise tenancy model.
--
--   Organization  = the firm (Deloitte India). SSO domain, cross-workspace roster.
--   Workspace     = ONE CLIENT ENGAGEMENT. This is the Chinese wall: the Airtel bid team
--                   structurally cannot read Jio's profile_financials, because the wall is
--                   the same workspace_id = current_workspace_id() policy already tested.
--   Project       = a pursuit within a workspace (migration 0014).
--
-- current_workspace_id() stays a SCALAR — deliberately, and this is the whole safety
-- argument. apps/web has no tenancy code: 24 server-component queries rely entirely on RLS
-- and nine have no WHERE clause at all. A set-returning resolver would silently merge
-- workspaces on 12 pages with HTTP 200s. One active workspace keeps every one of those
-- queries correct, unchanged.
--
-- Backfill moves NO data — rows keep their scope value; only the resolver changes.
-- Idempotent.

-- ---------- organizations ----------
create table if not exists public.organizations (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  sso_domain text,                     -- SSO/SCIM hook (later phase); unused today
  created_at timestamptz not null default now()
);

alter table public.workspaces      add column if not exists org_id uuid references public.organizations(id);
alter table public.profiles        add column if not exists active_workspace_id uuid references public.workspaces(id);
alter table public.profiles        add column if not exists org_id uuid references public.organizations(id);
alter table public.profiles        add column if not exists is_org_admin boolean not null default false;

-- ---------- membership (user x workspace x role) ----------
create table if not exists public.workspace_members (
  user_id      uuid not null references auth.users(id) on delete cascade,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  role         public.user_role not null default 'writer',
  added_by     uuid,
  created_at   timestamptz not null default now(),
  primary key (user_id, workspace_id)
);
create index if not exists workspace_members_ws_idx on public.workspace_members(workspace_id);

-- ---------- the resolver ----------
-- Header first, then the stored active workspace — BOTH validated against membership, so a
-- forged or stale id for a workspace you are not in yields NULL. `workspace_id = NULL` is
-- never true, so every table returns zero rows: it fails CLOSED, with no error and no leak.
-- Revoking a membership row therefore nulls that user's scope on their very next request,
-- which is the entire deprovisioning mechanism.
--
-- ponytail: active_workspace_id is per-user, so two browser tabs on different workspaces
-- race (reads show permitted-but-confusing data; mutations 404). Unreachable while nobody
-- holds two memberships. Upgrade path: put the workspace in the URL (/w/[slug]/...) and
-- send x-workspace-id — this function already prefers it, so that change is routing only.
create or replace function public.current_workspace_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select m.workspace_id
  from public.workspace_members m
  where m.user_id = auth.uid()
    and m.workspace_id = coalesce(
      nullif(current_setting('request.headers', true)::json ->> 'x-workspace-id', '')::uuid,
      (select p.active_workspace_id from public.profiles p where p.user_id = auth.uid())
    )
  limit 1
$$;

-- Every workspace the caller can reach — for the switcher and the org roster. A SET is the
-- right answer HERE and only here; every data table stays scalar-scoped.
create or replace function public.current_workspace_member_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public
as $$
  select m.user_id from public.workspace_members m
  where m.workspace_id = public.current_workspace_id()
$$;

-- ---------- RLS ----------
alter table public.organizations     enable row level security;
alter table public.workspace_members enable row level security;

drop policy if exists organizations_member_select on public.organizations;
create policy organizations_member_select on public.organizations for select
  using (id = (select p.org_id from public.profiles p where p.user_id = auth.uid()));

-- The switcher needs every workspace you can reach, so this one IS a set.
drop policy if exists workspaces_member_select on public.workspaces;
create policy workspaces_member_select on public.workspaces for select
  using (exists (select 1 from public.workspace_members m
                 where m.workspace_id = workspaces.id and m.user_id = auth.uid()));

-- RECURSION RULE: the bootstrap policy is a bare column comparison and must NEVER call a
-- function that reads this table. The roster arm may, because current_workspace_id() is
-- security definer and this table does not set FORCE ROW LEVEL SECURITY — so the function's
-- own read is not re-filtered and the policy does not re-enter.
-- Do NOT add `alter table public.workspace_members force row level security`.
drop policy if exists workspace_members_self on public.workspace_members;
create policy workspace_members_self on public.workspace_members for select
  using (user_id = auth.uid());

drop policy if exists workspace_members_roster on public.workspace_members;
create policy workspace_members_roster on public.workspace_members for select
  using (workspace_id = public.current_workspace_id());

-- No INSERT/UPDATE/DELETE policy for `authenticated`: membership is written by the ENGINE
-- via the service role, same posture as audit_events. A client-writable membership table
-- would let any user grant themselves 'admin'. Keep these dropped.
drop policy if exists workspace_members_write on public.workspace_members;
drop policy if exists workspace_members_all on public.workspace_members;

-- ---------- backfill ----------
insert into public.organizations (name)
  select w.name from public.workspaces w
  where not exists (select 1 from public.organizations o where o.name = w.name);

update public.workspaces w set org_id = o.id
  from public.organizations o where o.name = w.name and w.org_id is null;

insert into public.workspace_members (user_id, workspace_id, role)
  select p.user_id, p.workspace_id, p.role from public.profiles p
  where p.workspace_id is not null
  on conflict (user_id, workspace_id) do nothing;

update public.profiles p
   set active_workspace_id = coalesce(p.active_workspace_id, p.workspace_id),
       org_id              = coalesce(p.org_id, w.org_id),
       is_org_admin        = (p.role = 'admin')
  from public.workspaces w
 where w.id = p.workspace_id;

-- profiles.workspace_id is dead after this migration but kept as the rollback lifeline;
-- dropped in 0015 once the isolation suite has run green against live data.
alter table public.profiles alter column workspace_id drop not null;

-- ---------- assert the backfill is complete ----------
do $$ begin
  if exists (
    select 1 from public.profiles p
    where p.workspace_id is not null
      and not exists (select 1 from public.workspace_members m
                      where m.user_id = p.user_id and m.workspace_id = p.workspace_id)
  ) then
    raise exception 'backfill incomplete: a profile has no matching membership row';
  end if;
  if exists (select 1 from public.profiles where active_workspace_id is null
             and workspace_id is not null) then
    raise exception 'backfill incomplete: a profile has no active workspace';
  end if;
end $$;
