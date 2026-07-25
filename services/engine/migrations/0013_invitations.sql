-- Invitations + a roster that can actually render more than one person.
--
-- Today there is NO way to add a second human to a workspace: no endpoint, no UI, no
-- signup. Onboarding means running a dev-only seed script that deletes the user first.
--
-- Two structural blockers fixed here:
--   1. profiles has no name/email, so a roster renders truncated UUIDs.
--   2. profiles_self_select is `user_id = auth.uid()` where every sibling table scopes by
--      workspace — so the members table was structurally incapable of showing anyone but
--      yourself. That reads like a copy-paste omission, not a decision.
-- Idempotent.

-- ---------- identity for the roster ----------
-- Denormalized from the verified JWT at invite-accept. auth.users is not readable through
-- PostgREST from a client, so a roster cannot join to it.
alter table public.profiles add column if not exists full_name text;
alter table public.profiles add column if not exists email      text;

-- ---------- invitations ----------
create table if not exists public.workspace_invitations (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  email        text not null,
  role         public.user_role not null default 'writer',
  invited_by   uuid not null,
  -- sha256 of a 32-byte random token. The raw token is returned to the inviter ONCE and
  -- never stored, so a database read cannot be replayed into workspace membership.
  token_hash   text not null unique,
  expires_at   timestamptz not null default now() + interval '7 days',
  accepted_at  timestamptz,
  accepted_by  uuid,
  created_at   timestamptz not null default now()
);

-- One live invitation per email per workspace; re-inviting replaces rather than stacks.
create unique index if not exists workspace_invitations_pending
  on public.workspace_invitations (workspace_id, lower(email)) where accepted_at is null;
create index if not exists workspace_invitations_ws_idx
  on public.workspace_invitations(workspace_id);

alter table public.workspace_invitations enable row level security;
-- No policy for `authenticated` at all: invitations are engine-only, same posture as
-- audit_events and workspace_members. A readable invitations table hands out join tokens.
drop policy if exists workspace_invitations_all on public.workspace_invitations;

-- ---------- the roster ----------
-- Split into self + roster. The roster arm needs a definer helper because a plain subquery
-- on workspace_members runs under invoker RLS and would see only your OWN membership row —
-- returning you to the one-row bug this migration exists to fix.
drop policy if exists profiles_self_select on public.profiles;

drop policy if exists profiles_self on public.profiles;
create policy profiles_self on public.profiles for select
  using (user_id = auth.uid());

drop policy if exists profiles_roster on public.profiles;
create policy profiles_roster on public.profiles for select
  using (user_id in (select public.current_workspace_member_ids()));
