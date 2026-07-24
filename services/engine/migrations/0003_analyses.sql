-- M2: stored eligibility analyses (one latest per tender). RLS tenant-scoped. Idempotent.

create table if not exists public.analyses (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references public.tenants(id) on delete cascade,
  tender_id  uuid not null references public.tenders(id) on delete cascade,
  result     jsonb not null,
  created_at timestamptz not null default now(),
  unique (tender_id)
);
create index if not exists analyses_tenant_idx on public.analyses(tenant_id);

alter table public.analyses enable row level security;

drop policy if exists analyses_tenant_all on public.analyses;
create policy analyses_tenant_all on public.analyses for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());
