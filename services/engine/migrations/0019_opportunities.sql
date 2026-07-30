-- Module F — the opportunity feed (tendercraft-discovery-PRD.md §3).
--
-- Three tables, and the shape of them is the whole design:
--
--   opportunities        the SHARED public corpus. No workspace_id, on purpose — see below.
--   opportunity_matches  one row per (workspace, opportunity): what THIS workspace's rules
--                        decided, who owns it, whether it is watched. Workspace-scoped, RLS'd.
--   discovery_rules      the named, user-authored rules that are the ONLY thing permitted to
--                        move an item out of the primary feed (G-9 / F-AC6).
--
-- ── Why `opportunities` has no workspace_id ──────────────────────────────────────────────
--
-- CLAUDE.md says every table gets tenant_id + RLS + an isolation test, and this is the
-- documented exception. A GeM bid is public procurement data published by the Government of
-- India to the world; it is not any workspace's information. Copying 48,000 rows per workspace
-- would duplicate a public corpus per tenant, re-parse every document per tenant, and multiply
-- our request volume against a government portal by the number of customers — which is the one
-- thing G-10's rate discipline exists to prevent.
--
-- The isolation guarantee is preserved where it actually matters: **nothing a workspace does is
-- stored here.** Rules, verdicts, assignment, watch state and eligibility outcomes all live in
-- `opportunity_matches`, which is workspace-scoped and RLS'd exactly like every other table. Two
-- workspaces reading `opportunities` see identical public rows and can infer nothing about each
-- other. A consultant running client A and client B sees one shared list of public tenders and
-- two entirely separate sets of decisions about it (F-US3).
--
-- The table is still RLS-enabled: readable by any authenticated user, writable by nobody. Only
-- the service-role ingest path (which bypasses RLS) inserts. There is deliberately no INSERT,
-- UPDATE or DELETE policy — a logged-in user cannot write to the shared corpus at all.

do $$ begin
  create type public.opportunity_state as enum ('in_scope', 'excluded');
exception when duplicate_object then null; end $$;

do $$ begin
  -- Depth-1 triage only (C-FR6). Never feeds a Bid/No-Bid card; that stays Depth 2.
  create type public.eligibility_signal as enum (
    'likely_eligible', 'likely_ineligible', 'unknown'
  );
exception when duplicate_object then null; end $$;

-- ── the shared corpus ────────────────────────────────────────────────────────────────────
create table if not exists public.opportunities (
  id                uuid primary key default gen_random_uuid(),
  source_id         text not null,
  -- F-FR6 / F-AC4: merge on an exact normalized ref and nothing else. This UNIQUE constraint is
  -- the zero-wrong-merges gate enforced by the database rather than by code — two distinct
  -- tenders cannot collapse into one row, and a re-run of ingest cannot duplicate one.
  portal_ref_no     text not null,
  title             text,
  authority         text,
  category_codes    text[] not null default '{}',
  geography         text,
  estimated_value   numeric,
  emd               numeric,
  published_at      timestamptz,
  closing_at        timestamptz,
  prebid_at         timestamptz,
  document_urls     text[] not null default '{}',
  -- F-FR2. The snapshot itself is retained privately as an audit record and served to nobody:
  -- GeM forbids reproducing its content without written permission (docs/discovery/source-gem.md §8).
  raw_snapshot_ref  text,
  source_fields     jsonb not null default '{}'::jsonb,
  -- Phase-2 deterministic parse of the bid document. Null until fetched; `extraction` inside
  -- records HOW it was obtained, and it is never 'model' for these fields.
  eligibility       jsonb,
  eligibility_at    timestamptz,
  first_seen_at     timestamptz not null default now(),
  last_seen_at      timestamptz not null default now(),
  unique (source_id, portal_ref_no)
);
create index if not exists opportunities_closing_idx  on public.opportunities(closing_at);
create index if not exists opportunities_category_idx on public.opportunities using gin (category_codes);
create index if not exists opportunities_seen_idx     on public.opportunities(last_seen_at desc, id desc);

-- ── per-workspace decisions ──────────────────────────────────────────────────────────────
create table if not exists public.opportunity_matches (
  id                 uuid primary key default gen_random_uuid(),
  workspace_id       uuid not null references public.workspaces(id) on delete cascade,
  opportunity_id     uuid not null references public.opportunities(id) on delete cascade,
  state              public.opportunity_state not null default 'in_scope',
  -- The name of the user-authored rule that excluded this item. NOT a description, not a score:
  -- the rule's own name, so the UI can say "hidden by your 'Goods only' rule" (S14-D1).
  excluded_by_rule   text,
  eligibility        public.eligibility_signal not null default 'unknown',
  -- The criterion that decided it, e.g. "turnover ₹5,00,000 required vs ₹8.2 Cr on profile".
  -- C-AC9 requires every Depth-1 verdict to render its deciding criterion.
  eligibility_reason text,
  relevance_band     text,
  assigned_to        uuid,
  watched            boolean not null default false,
  computed_at        timestamptz not null default now(),
  unique (workspace_id, opportunity_id),
  -- ── G-9 / F-AC6, enforced by the database ──────────────────────────────────────────────
  -- An item may be excluded ONLY while naming the rule that excluded it, and an in-scope item
  -- may not carry a rule name. This makes model-driven exclusion structurally impossible rather
  -- than merely forbidden: there is no way to hide a tender without writing down which
  -- user-authored rule did it, and a model has no rule name to write. A missed tender is the
  -- one failure in this product with no natural feedback signal (ET-7), so the constraint lives
  -- in the schema where no code path can route around it.
  constraint opportunity_matches_exclusion_names_its_rule
    check ((state = 'excluded') = (excluded_by_rule is not null))
);
create index if not exists opportunity_matches_ws_state_idx
  on public.opportunity_matches(workspace_id, state);
create index if not exists opportunity_matches_opp_idx
  on public.opportunity_matches(opportunity_id);

-- ── the rules themselves ─────────────────────────────────────────────────────────────────
create table if not exists public.discovery_rules (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  name         text not null,
  enabled      boolean not null default true,
  -- A closed set, mirrored by app/deterministic/discovery.py's RULE_KINDS. If the UI ever lists
  -- these, say so in a comment at both ends — a UI array mirroring a server enum WILL drift
  -- (known-pitfalls, learned on the approval-stage enum).
  kind         text not null,
  spec         jsonb not null default '{}'::jsonb,
  created_by   uuid,
  created_at   timestamptz not null default now(),
  -- Rules are named so an exclusion can be explained. Two rules cannot share a name, or
  -- "hidden by your 'X' rule" stops identifying anything.
  unique (workspace_id, name)
);
create index if not exists discovery_rules_ws_idx on public.discovery_rules(workspace_id)
  where enabled;

-- ── RLS ──────────────────────────────────────────────────────────────────────────────────
alter table public.opportunities       enable row level security;
alter table public.opportunity_matches enable row level security;
alter table public.discovery_rules     enable row level security;

-- Public corpus: any authenticated user may read; NOBODY may write. The absence of an
-- INSERT/UPDATE/DELETE policy is deliberate and is the write protection — only the service-role
-- ingest path, which bypasses RLS, populates this table.
drop policy if exists opportunities_read_all on public.opportunities;
create policy opportunities_read_all on public.opportunities for select
  using (auth.uid() is not null);

drop policy if exists opportunity_matches_workspace_all on public.opportunity_matches;
create policy opportunity_matches_workspace_all on public.opportunity_matches for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

drop policy if exists discovery_rules_workspace_all on public.discovery_rules;
create policy discovery_rules_workspace_all on public.discovery_rules for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());
