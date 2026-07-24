-- M3 schema: content library + proposals (Module B). RLS tenant-scoped. Idempotent.

do $$ begin
  create type public.proposal_status as enum ('draft', 'review', 'compliance', 'approved', 'exported');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.draft_status as enum ('drafted', 'placeholder', 'missing', 'unverified');
exception when duplicate_object then null; end $$;

-- Library documents (evidence corpus). One text blob + validity + structured fields.
create table if not exists public.library_documents (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references public.tenants(id) on delete cascade,
  name              text not null,
  doc_type          text,                 -- 'financial'|'certification'|'completion'|'undertaking'|'cv'
  text_content      text not null default '',
  valid_to          date,                 -- null = evergreen
  structured_fields jsonb not null default '{}',
  uploaded_by       uuid,
  created_at        timestamptz not null default now()
);
create index if not exists library_tenant_idx on public.library_documents(tenant_id);

create table if not exists public.proposals (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references public.tenants(id) on delete cascade,
  tender_id  uuid not null references public.tenders(id) on delete cascade,
  status     public.proposal_status not null default 'draft',
  created_at timestamptz not null default now(),
  unique (tender_id)
);
create index if not exists proposals_tenant_idx on public.proposals(tenant_id);

-- One drafted response per criterion. `sentences` holds the cite-or-flag tagged draft.
create table if not exists public.proposal_responses (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  proposal_id   uuid not null references public.proposals(id) on delete cascade,
  criterion_id  uuid not null references public.criteria(id) on delete cascade,
  draft_text    text not null default '',
  sentences     jsonb not null default '[]',
  draft_status  public.draft_status not null default 'missing',
  flags         jsonb not null default '[]',
  created_at    timestamptz not null default now(),
  unique (proposal_id, criterion_id)
);
create index if not exists responses_proposal_idx on public.proposal_responses(proposal_id);

alter table public.library_documents   enable row level security;
alter table public.proposals           enable row level security;
alter table public.proposal_responses  enable row level security;

drop policy if exists library_documents_tenant_all on public.library_documents;
create policy library_documents_tenant_all on public.library_documents for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

drop policy if exists proposals_tenant_all on public.proposals;
create policy proposals_tenant_all on public.proposals for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

drop policy if exists proposal_responses_tenant_all on public.proposal_responses;
create policy proposal_responses_tenant_all on public.proposal_responses for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());
