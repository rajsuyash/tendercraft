-- Sev-1: scope the approval unique key by tenant.
--
-- `proposal_approvals` was `unique (proposal_id, stage)`. db.add_approval upserts with the
-- SERVICE ROLE (RLS bypassed), so that key was the only thing separating tenants — and
-- POST /api/proposals/{proposal_id}/approve took proposal_id straight from the path with no
-- ownership check. Tenant A posting to tenant B's proposal resolved to DO UPDATE and
-- rewrote tenant_id to A: B's approval row vanished and B's proposal silently became
-- non-exportable, with the audit row landing in A's trail.
--
-- This is the pitfall already recorded in docs/known-pitfalls.md ("Upsert on_conflict target
-- that omits tenant_id"), unpatched on this one path.
--
-- Widening the key can never violate existing rows, so this is safe on live data. The
-- matching on_conflict string in app/db.py MUST ship in the same deploy or every approval
-- 400s with "no unique constraint matching the ON CONFLICT specification". Idempotent.

alter table public.proposal_approvals
  drop constraint if exists proposal_approvals_proposal_id_stage_key;

do $$ begin
  alter table public.proposal_approvals
    add constraint proposal_approvals_tenant_proposal_stage_key
    unique (tenant_id, proposal_id, stage);
exception when duplicate_table then null; end $$;
