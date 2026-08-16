-- Tell a human a relevant tender arrived (UML ask 1).
--
-- The ask names a CRM. The sentence after it names the problem: "relevant tenders are
-- identified manually and circulated to the respective Zonal Heads." Routing answered the
-- circulation half in-product (migration 0019's assigned_to, M12); this answers the other
-- half — nobody is watching a feed at 9am, and a tender nobody opened is the same miss as a
-- tender nobody found (ET-7).
--
-- Two tables, and the second is the one that matters.
--
--   notification_settings  per workspace: is this on, who receives, and from which relevance
--                          band. Off by default — a product that starts emailing people
--                          because it was deployed is a product that gets filtered to spam,
--                          after which every later alert is invisible too.
--   notifications_sent     the ledger. One row per (workspace, opportunity, recipient), and
--                          the unique key IS the idempotency guarantee: a dispatcher that
--                          runs twice, or a retry after a partial failure, cannot re-send.
--                          It is also the audit answer to "did we tell anyone about this bid",
--                          which is the question asked after a deadline is missed.
--
-- Deliberately NOT here: an unsubscribe token, HTML templates, open tracking, a queue. This
-- sends a digest to a handful of colleagues who asked for it, not a marketing campaign.

create table if not exists public.notification_settings (
  workspace_id     uuid primary key references public.workspaces(id) on delete cascade,
  -- Off until someone turns it on, deliberately (see above).
  enabled          boolean not null default false,
  -- Addresses that receive the workspace digest. Members are notified individually when a
  -- tender is ASSIGNED to them; this list is for whoever wants the whole picture.
  recipients       text[] not null default '{}',
  -- Only alert at or above this relevance band. Never a hard filter on the FEED — the feed
  -- still shows everything (F-AC6/ET-7); this governs what is worth an email at 7am.
  min_band         text not null default 'medium',
  -- Alert the assignee when a tender is routed to them. This is the literal ask: "circulated
  -- to the respective Zonal Heads".
  notify_assignee  boolean not null default true,
  updated_by       uuid,
  updated_at       timestamptz not null default now(),
  created_at       timestamptz not null default now()
);

create table if not exists public.notifications_sent (
  id             uuid primary key default gen_random_uuid(),
  workspace_id   uuid not null references public.workspaces(id) on delete cascade,
  opportunity_id uuid not null references public.opportunities(id) on delete cascade,
  recipient      text not null,
  kind           text not null default 'digest',   -- 'digest' | 'assignment'
  sent_at        timestamptz not null default now(),
  -- workspace_id inside the key: the engine writes with the service role and bypasses RLS,
  -- so a conflict target that omits the scope column can reassign another workspace's row
  -- (docs/known-pitfalls.md, learned the hard way on 0027).
  unique (workspace_id, opportunity_id, recipient, kind)
);
create index if not exists notifications_sent_ws_idx on public.notifications_sent(workspace_id);

alter table public.notification_settings enable row level security;
alter table public.notifications_sent    enable row level security;

drop policy if exists notification_settings_workspace_all on public.notification_settings;
create policy notification_settings_workspace_all on public.notification_settings for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

drop policy if exists notifications_sent_workspace_all on public.notifications_sent;
create policy notifications_sent_workspace_all on public.notifications_sent for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

comment on column public.notification_settings.min_band is
  'Governs what is worth an EMAIL, never what appears in the feed. An alert threshold that '
  'silently narrowed the feed would be an exclusion no user authored (G-9/F-AC6).';

comment on table public.notifications_sent is
  'Idempotency and audit in one table. The unique key is what stops a re-run re-sending; the '
  'rows are what answers "was anyone told about this bid" after a deadline is missed.';
