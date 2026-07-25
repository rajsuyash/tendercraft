-- Long-form proposal sections (Module B). The document layer.
--
-- proposal_responses stays untouched: it is the COMPLIANCE layer (unique per criterion,
-- feeds build_matrix / mandatory_coverage / readiness). Sections are a second layer that
-- reference it, so no gate or existing test changes shape.
--
-- RLS tenant-scoped; tenant_id sits in the unique key so a service-role upsert merge can
-- never reassign another tenant's row (the cross-tenant-upsert pitfall from 0007). Idempotent.

create table if not exists public.proposal_sections (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references public.tenants(id) on delete cascade,
  proposal_id  uuid not null references public.proposals(id) on delete cascade,
  key          text not null,                      -- stable slug from SECTION_SPECS
  parent_key   text,                               -- one level of nesting only
  heading      text not null,
  order_index  int  not null,
  kind         text not null,                      -- 'narrative' | 'assembled' | 'compliance'
  body_md      text not null default '',
  sentences    jsonb not null default '[]'::jsonb, -- tagged sentences (cls, citations, source_ref)
  status       text not null default 'drafted',    -- 'drafted' | 'placeholder' | 'unverified'
  confidence   numeric,
  flags        jsonb not null default '[]'::jsonb,
  word_count   int  not null default 0,
  approved_by  uuid,
  approved_at  timestamptz,
  created_at   timestamptz not null default now(),
  unique (tenant_id, proposal_id, key)
);

create index if not exists proposal_sections_proposal_idx
  on public.proposal_sections(proposal_id);
create index if not exists proposal_sections_tenant_idx
  on public.proposal_sections(tenant_id);

alter table public.proposal_sections enable row level security;

drop policy if exists proposal_sections_tenant_all on public.proposal_sections;
create policy proposal_sections_tenant_all on public.proposal_sections for all
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());
