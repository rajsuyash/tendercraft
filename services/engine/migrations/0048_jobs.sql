-- One row per long-running unit of work started on a user's behalf.
--
-- WHY THIS EXISTS: `/prepare` ran 418s on a 450-criterion tender while the web tier's request
-- timeout was 300s, so the browser was told "Action failed" about work that had already
-- succeeded. A job row is what lets the answer outlive the request that asked for it.
--
-- `kind` is generic on purpose but exactly one value ships today. A second kind is a decision,
-- not a fill-in-the-blank.
create table if not exists public.jobs (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.workspaces(id) on delete cascade,
  tender_id     uuid references public.tenders(id) on delete cascade,
  kind          text not null check (kind in ('prepare')),
  state         text not null default 'queued'
                check (state in ('queued','running','succeeded','failed')),
  -- The stage the UI names while it waits, and the resume point on retry.
  stage         text,
  -- Stages already finished, so a redelivery does not re-pay for model calls.
  done_stages   text[] not null default '{}',
  error_code    text,
  error_message text,
  attempts      int not null default 0,
  created_at    timestamptz not null default now(),
  started_at    timestamptz,
  finished_at   timestamptz
);

create index if not exists jobs_workspace_created_idx
  on public.jobs (workspace_id, created_at desc);

-- One live job per tender+kind. A partial unique index rather than an application check:
-- the 2026-09-28 defect made users re-click work that was already running, and two concurrent
-- prepares would double-write the analysis and the proposal.
create unique index if not exists jobs_one_active_per_tender
  on public.jobs (tender_id, kind)
  where state in ('queued','running');

alter table public.jobs enable row level security;

-- Readers see only their own workspace's jobs. The engine writes with the service role, which
-- bypasses RLS, and scopes every query in code the way `auth.py` mirrors current_workspace_id().
drop policy if exists jobs_select_own_workspace on public.jobs;
create policy jobs_select_own_workspace on public.jobs
  for select using (workspace_id = public.current_workspace_id());
