-- TenderCraft schema v0 — tenants, RBAC profiles, tenders, TOM criteria, audit.
-- Every tenant-scoped table carries tenant_id + RLS (ET-6 zero-tolerance isolation).
-- Idempotent: safe to re-apply.

create extension if not exists pgcrypto;

-- ---------- enums ----------
do $$ begin
  create type public.user_role as enum
    ('writer','reviewer','compliance_checker','legal','approver','admin');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.tender_status as enum
    ('uploaded','processing','verification','locked','failed');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.criterion_category as enum
    ('eligibility','technical','financial','terms');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.requirement_level as enum
    ('mandatory','desirable','self_attestation');
exception when duplicate_object then null; end $$;

-- ---------- tables ----------
create table if not exists public.tenants (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  created_at timestamptz not null default now()
);

-- Links a Supabase auth user to exactly one tenant + a role (E-FR1 RBAC).
create table if not exists public.profiles (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  tenant_id  uuid not null references public.tenants(id) on delete cascade,
  role       public.user_role not null default 'writer',
  created_at timestamptz not null default now()
);
create index if not exists profiles_tenant_idx on public.profiles(tenant_id);

create table if not exists public.tenders (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  title         text not null,
  tender_number text,
  authority     text,
  deadline      timestamptz,
  status        public.tender_status not null default 'uploaded',
  locked_at     timestamptz,
  created_at    timestamptz not null default now()
);
create index if not exists tenders_tenant_idx on public.tenders(tenant_id);

-- One row of the Tender Object Model (A: source-anchored criteria).
create table if not exists public.criteria (
  id                uuid primary key default gen_random_uuid(),
  tender_id         uuid not null references public.tenders(id) on delete cascade,
  tenant_id         uuid not null references public.tenants(id) on delete cascade,
  verbatim_text     text not null,
  category          public.criterion_category not null,
  requirement_level public.requirement_level not null,
  evidence_required text,
  evaluation_weight numeric,
  confidence        numeric not null check (confidence >= 0 and confidence <= 1),
  confirmed         boolean not null default false,
  anchor_page       int,
  anchor_clause     text,
  created_at        timestamptz not null default now()
);
create index if not exists criteria_tender_idx on public.criteria(tender_id);
create index if not exists criteria_tenant_idx on public.criteria(tenant_id);

-- Append-only audit trail (E-FR4 / E-AC1). Immutability enforced by trigger below.
create table if not exists public.audit_events (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references public.tenants(id) on delete cascade,
  actor      uuid,
  action     text not null,
  entity     text not null,
  entity_id  uuid,
  before     jsonb,
  after      jsonb,
  created_at timestamptz not null default now()
);
create index if not exists audit_tenant_idx on public.audit_events(tenant_id);

-- ---------- tenant lookup (security definer: reads the caller's own profile) ----------
create or replace function public.current_tenant_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select tenant_id from public.profiles where user_id = auth.uid()
$$;

-- ---------- append-only enforcement for audit_events ----------
create or replace function public.block_mutation()
returns trigger language plpgsql as $$
begin
  raise exception 'audit_events is append-only (E-AC1)';
end $$;

drop trigger if exists audit_no_update on public.audit_events;
create trigger audit_no_update before update on public.audit_events
  for each row execute function public.block_mutation();

drop trigger if exists audit_no_delete on public.audit_events;
create trigger audit_no_delete before delete on public.audit_events
  for each row execute function public.block_mutation();

-- Row triggers do NOT fire on TRUNCATE; a statement-level guard closes that bypass.
drop trigger if exists audit_no_truncate on public.audit_events;
create trigger audit_no_truncate before truncate on public.audit_events
  for each statement execute function public.block_mutation();

-- ---------- RLS: enabled on every table; policies scope to the caller's tenant ----------
alter table public.tenants      enable row level security;
alter table public.profiles     enable row level security;
alter table public.tenders      enable row level security;
alter table public.criteria     enable row level security;
alter table public.audit_events enable row level security;

drop policy if exists profiles_self_select on public.profiles;
create policy profiles_self_select on public.profiles
  for select using (user_id = auth.uid());

drop policy if exists tenants_member_select on public.tenants;
create policy tenants_member_select on public.tenants
  for select using (id = public.current_tenant_id());

drop policy if exists tenders_tenant_all on public.tenders;
create policy tenders_tenant_all on public.tenders
  for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

drop policy if exists criteria_tenant_all on public.criteria;
create policy criteria_tenant_all on public.criteria
  for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

-- Audit: tenant-scoped READ for the audit-log UI (S12). No write policy for the
-- authenticated role — the ENGINE writes audit rows via the service role (which bypasses
-- RLS), so clients can never forge or attribute audit entries (E-FR4 trustworthiness).
-- UPDATE/DELETE/TRUNCATE are blocked for every role by the triggers above (E-AC1).
drop policy if exists audit_tenant_select on public.audit_events;
create policy audit_tenant_select on public.audit_events
  for select using (tenant_id = public.current_tenant_id());

-- Removed: a client-writable insert policy would let a user forge un-deletable audit rows.
drop policy if exists audit_tenant_insert on public.audit_events;
