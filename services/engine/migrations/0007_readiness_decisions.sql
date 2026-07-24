-- Per-criterion bidder decisions on readiness items. Survives re-match (proposal_responses
-- is overwritten on every prepare, so decisions cannot live there). RLS tenant-scoped. Idempotent.

create table if not exists public.readiness_decisions (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  tender_id     uuid not null references public.tenders(id) on delete cascade,
  criterion_id  uuid not null references public.criteria(id) on delete cascade,
  decision      text not null default 'resolve',   -- 'resolve'|'ignore'|'do_not_proceed'
  comment       text not null default '',
  document_id   uuid references public.library_documents(id) on delete set null,  -- optional attached doc
  updated_by    uuid,
  updated_at    timestamptz not null default now(),
  -- tenant_id in the key so an upsert merge can never cross tenants (ET-6 defense-in-depth).
  unique (tenant_id, tender_id, criterion_id)
);
create index if not exists readiness_decisions_tenant_idx on public.readiness_decisions(tenant_id);

alter table public.readiness_decisions enable row level security;

drop policy if exists readiness_decisions_tenant_all on public.readiness_decisions;
create policy readiness_decisions_tenant_all on public.readiness_decisions for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());
