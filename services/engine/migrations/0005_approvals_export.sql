-- M4 schema: approval chain + export state (Module E). RLS tenant-scoped. Idempotent.

alter table public.proposals add column if not exists approvals_required int not null default 2;
alter table public.proposals add column if not exists exported_at timestamptz;

create table if not exists public.proposal_approvals (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  proposal_id uuid not null references public.proposals(id) on delete cascade,
  stage       text not null,               -- 'review' | 'compliance' | 'approver'
  approver    uuid,
  approved_at timestamptz not null default now(),
  unique (proposal_id, stage)
);
create index if not exists approvals_proposal_idx on public.proposal_approvals(proposal_id);

alter table public.proposal_approvals enable row level security;

drop policy if exists proposal_approvals_tenant_all on public.proposal_approvals;
create policy proposal_approvals_tenant_all on public.proposal_approvals for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());
