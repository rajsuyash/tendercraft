-- M2 schema: vendor profile (Module C). Eligibility runs against this structured data.
-- Every table tenant-scoped with RLS (ET-6). Idempotent.

create table if not exists public.vendor_profiles (
  tenant_id           uuid primary key references public.tenants(id) on delete cascade,
  cin                 text,
  pan                 text,
  gst                 text,
  udyam_registration  text,
  dpiit_registered    boolean not null default false,
  net_worth_cr        numeric,
  working_capital_cr  numeric,
  oem_status          text,          -- 'oem' | 'system_integrator' | 'trader'
  updated_at          timestamptz not null default now()
);

create table if not exists public.profile_financials (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  fy_label    text not null,          -- 'FY23'
  turnover_cr numeric not null,
  unique (tenant_id, fy_label)
);

create table if not exists public.experience_records (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references public.tenants(id) on delete cascade,
  project_name    text not null,
  client_type     text,               -- 'govt' | 'psu' | 'private'
  value_cr        numeric,
  scope_tags      text[] not null default '{}',
  completion_date date,
  evidence_ref    text,
  created_at      timestamptz not null default now()
);
create index if not exists experience_tenant_idx on public.experience_records(tenant_id);

create table if not exists public.certifications (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references public.tenants(id) on delete cascade,
  name       text not null,           -- 'ISO 9001:2015'
  cert_no    text,
  valid_from date,
  valid_to   date,
  created_at timestamptz not null default now()
);
create index if not exists certifications_tenant_idx on public.certifications(tenant_id);

-- RLS: every table scoped to the caller's tenant (same pattern as 0001).
alter table public.vendor_profiles    enable row level security;
alter table public.profile_financials enable row level security;
alter table public.experience_records enable row level security;
alter table public.certifications     enable row level security;

drop policy if exists vendor_profiles_tenant_all on public.vendor_profiles;
create policy vendor_profiles_tenant_all on public.vendor_profiles for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

drop policy if exists profile_financials_tenant_all on public.profile_financials;
create policy profile_financials_tenant_all on public.profile_financials for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

drop policy if exists experience_records_tenant_all on public.experience_records;
create policy experience_records_tenant_all on public.experience_records for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

drop policy if exists certifications_tenant_all on public.certifications;
create policy certifications_tenant_all on public.certifications for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());
