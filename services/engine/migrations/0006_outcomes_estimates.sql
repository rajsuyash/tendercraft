-- M5 schema: outcome corpus + stored score estimates (Module D). RLS scoped. Idempotent.

create table if not exists public.outcomes (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references public.tenants(id) on delete cascade,
  authority_cluster text not null,        -- e.g. 'NIC' / 'GeM' / state
  category_cluster  text not null,        -- e.g. 'it-hardware'
  won              boolean,
  rejection_stage  text,
  technical_score  numeric,               -- disclosed technical score, if known
  created_at       timestamptz not null default now()
);
create index if not exists outcomes_cluster_idx on public.outcomes(tenant_id, authority_cluster, category_cluster);

create table if not exists public.score_estimates (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references public.tenants(id) on delete cascade,
  tender_id  uuid not null references public.tenders(id) on delete cascade,
  result     jsonb not null,
  created_at timestamptz not null default now(),
  unique (tender_id)
);

alter table public.outcomes        enable row level security;
alter table public.score_estimates enable row level security;

drop policy if exists outcomes_tenant_all on public.outcomes;
create policy outcomes_tenant_all on public.outcomes for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

drop policy if exists score_estimates_tenant_all on public.score_estimates;
create policy score_estimates_tenant_all on public.score_estimates for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());
