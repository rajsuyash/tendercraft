-- Pure rename: tenant -> workspace. NO semantic change whatsoever.
--
-- Why: after 0011 a "tenant" becomes an ORGANIZATION (the firm) and the isolation boundary
-- becomes a WORKSPACE (a client engagement). Leaving the column named tenant_id would mean
-- the column named after the wrong concept is the one enforcing isolation — which is
-- precisely how someone later writes a cross-workspace query.
--
-- Safe because Postgres rewrites dependent objects automatically on a column rename:
-- foreign keys, indexes, unique constraints AND stored policy expressions all follow, since
-- policies are stored parsed rather than as text. The 15 identical tenant policies therefore
-- need zero edits. Function references follow by OID, so renaming the function keeps every
-- policy pointing at it.
--
-- The one thing that does NOT follow: a `language sql` function BODY is stored as source
-- text, so current_tenant_id()'s body still names profiles.tenant_id after the rename and
-- must be replaced explicitly (done at the end).
--
-- Not idempotent by nature (a rename cannot be re-applied), so each step is guarded.

-- ---------- 1. the table ----------
do $$ begin
  if exists (select 1 from pg_tables where schemaname = 'public' and tablename = 'tenants') then
    alter table public.tenants rename to workspaces;
  end if;
end $$;

-- ---------- 2. the 17 scope columns ----------
do $$
declare t text;
begin
  foreach t in array array[
    'analyses','audit_events','certifications','criteria','experience_records',
    'library_documents','outcomes','profile_financials','profiles','proposal_approvals',
    'proposal_responses','proposal_sections','proposals','readiness_decisions',
    'score_estimates','tenders','vendor_profiles'
  ] loop
    if exists (
      select 1 from information_schema.columns
      where table_schema = 'public' and table_name = t and column_name = 'tenant_id'
    ) then
      execute format('alter table public.%I rename column tenant_id to workspace_id', t);
    end if;
  end loop;
end $$;

-- ---------- 3. the resolver ----------
do $$ begin
  if exists (
    select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname = 'current_tenant_id'
  ) then
    alter function public.current_tenant_id() rename to current_workspace_id;
  end if;
end $$;

-- Body must be rewritten by hand: it still reads `select tenant_id from profiles`.
create or replace function public.current_workspace_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select workspace_id from public.profiles where user_id = auth.uid()
$$;

-- ---------- 4. policy + index labels (cosmetic, but grep-honest) ----------
do $$
declare r record;
begin
  for r in
    select schemaname, tablename, policyname from pg_policies
    where schemaname = 'public' and policyname like '%tenant%'
  loop
    execute format('alter policy %I on public.%I rename to %I',
                   r.policyname, r.tablename, replace(r.policyname, 'tenant', 'workspace'));
  end loop;

  for r in
    select indexname from pg_indexes
    where schemaname = 'public' and indexname like '%tenant%'
  loop
    execute format('alter index public.%I rename to %I',
                   r.indexname, replace(r.indexname, 'tenant', 'workspace'));
  end loop;
end $$;
