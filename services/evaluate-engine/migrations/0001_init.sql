-- TenderCraft Evaluate — schema v0 (M0)
--
-- Every table carries authority_id and an RLS policy. The financial table carries a SECOND
-- policy keyed on the evaluation's technical-lock state: the sealed-bid rule is enforced in
-- SQL, not only in the handler, so a query that forgets to check still cannot read an amount.

create extension if not exists "pgcrypto";

-- ── tenancy ────────────────────────────────────────────────────────────────────
create table authorities (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  created_at  timestamptz not null default now()
);

create table authority_members (
  id            uuid primary key default gen_random_uuid(),
  authority_id  uuid not null references authorities(id) on delete cascade,
  user_id       uuid not null,
  email         text not null,
  full_name     text,
  role          text not null check (role in ('officer','member','chair','auditor')),
  created_at    timestamptz not null default now(),
  unique (authority_id, user_id)
);

create table profiles (
  user_id               uuid primary key,
  email                 text not null,
  active_authority_id   uuid references authorities(id) on delete set null
);

-- Resolves the caller's authority server-side. Mirrors the bidder-side pattern that was
-- hardened by a live isolation suite: header-preferred, ALWAYS membership-validated,
-- returns a scalar so a page with no WHERE clause cannot merge tenants.
create or replace function current_authority_id() returns uuid
language sql stable security definer set search_path = public as $$
  select a.authority_id from authority_members a
  where a.user_id = auth.uid()
    and a.authority_id = coalesce(
      nullif(current_setting('request.headers', true)::json->>'x-authority-id','')::uuid,
      (select p.active_authority_id from profiles p where p.user_id = auth.uid())
    )
  limit 1
$$;

-- ── evaluations ────────────────────────────────────────────────────────────────
create table evaluations (
  id                  uuid primary key default gen_random_uuid(),
  authority_id        uuid not null references authorities(id) on delete cascade,
  title               text not null,
  tender_number       text,
  state               text not null default 'active' check (state in ('active','concluded','archived')),
  -- published framework, frozen at framework_locked_at
  technical_weight    int  not null default 70,
  financial_weight    int  not null default 30,
  qualifying_marks    int  not null default 65,
  tie_break_rule      text,                    -- extracted from the RFP if it states one
  quorum              int  not null default 3,
  framework_locked_at timestamptz,
  framework_locked_by uuid,
  technical_locked_at timestamptz,
  technical_locked_by uuid,
  created_at          timestamptz not null default now(),
  check (technical_weight + financial_weight = 100)
);

create table criteria (
  id                uuid primary key default gen_random_uuid(),
  authority_id      uuid not null references authorities(id) on delete cascade,
  evaluation_id     uuid not null references evaluations(id) on delete cascade,
  kind              text not null check (kind in ('pq','technical')),
  text              text not null,
  max_marks         int  not null default 0,
  -- deterministic comparison for pq criteria: numeric | date | boolean | qualitative
  compare_kind      text not null default 'qualitative'
                    check (compare_kind in ('numeric','date','boolean','qualitative')),
  compare_op        text,                       -- '>=' | '<=' | '=' | 'present'
  compare_value     text,
  anchor_page       int,
  anchor_clause     text,
  confidence        numeric not null default 1.0,
  confirmed         boolean not null default false,
  order_index       int not null default 0
);

create table bids (
  id             uuid primary key default gen_random_uuid(),
  authority_id   uuid not null references authorities(id) on delete cascade,
  evaluation_id  uuid not null references evaluations(id) on delete cascade,
  bidder_name    text not null,
  responsive     boolean,                       -- null = not yet screened
  responsive_reason text,
  screened_by    uuid,
  created_at     timestamptz not null default now(),
  unique (evaluation_id, bidder_name)
);

-- Each bid's extracted answer to each criterion, with a page anchor into the submission.
create table bid_responses (
  id             uuid primary key default gen_random_uuid(),
  authority_id   uuid not null references authorities(id) on delete cascade,
  bid_id         uuid not null references bids(id) on delete cascade,
  criterion_id   uuid not null references criteria(id) on delete cascade,
  stated_value   text,                          -- null => "Not stated" (never assumed to fail)
  excerpt        text,
  anchor_page    int,
  unique (bid_id, criterion_id)
);

-- SEALED. Separate table on purpose (PRD F5-AC1): the financial envelope is split from the
-- technical one at ingest, and no read path returns `amount_inr` before technical lock.
create table bid_financials (
  id            uuid primary key default gen_random_uuid(),
  authority_id  uuid not null references authorities(id) on delete cascade,
  bid_id        uuid not null references bids(id) on delete cascade unique,
  amount_inr    numeric not null,
  opened_at     timestamptz,
  opened_by     uuid
);

create table coi_declarations (
  id            uuid primary key default gen_random_uuid(),
  authority_id  uuid not null references authorities(id) on delete cascade,
  evaluation_id uuid not null references evaluations(id) on delete cascade,
  user_id       uuid not null,
  has_interest  boolean not null,
  detail        text,
  filed_at      timestamptz not null default now(),
  unique (evaluation_id, user_id)
);

-- One row per member × bid × criterion. pre_reveal_mark is what makes the deference metric
-- (F7-AC5) computable — it is the evaluator's own judgement before the AI proposal was shown.
create table scores (
  id                  uuid primary key default gen_random_uuid(),
  authority_id        uuid not null references authorities(id) on delete cascade,
  evaluation_id       uuid not null references evaluations(id) on delete cascade,
  bid_id              uuid not null references bids(id) on delete cascade,
  criterion_id        uuid not null references criteria(id) on delete cascade,
  evaluator_id        uuid not null,
  pre_reveal_mark     numeric not null,
  ai_proposed_mark    numeric,
  final_mark          numeric not null,
  rationale           text not null,
  amended_after_reveal boolean not null default false,
  submitted_at        timestamptz not null default now(),
  unique (bid_id, criterion_id, evaluator_id)
);

-- Consensus is a SEPARATE row so the individual marks that justified it are never overwritten.
create table consensus_marks (
  id            uuid primary key default gen_random_uuid(),
  authority_id  uuid not null references authorities(id) on delete cascade,
  evaluation_id uuid not null references evaluations(id) on delete cascade,
  bid_id        uuid not null references bids(id) on delete cascade,
  criterion_id  uuid not null references criteria(id) on delete cascade,
  agreed_mark   numeric not null,
  note          text not null,
  chair_id      uuid not null,
  recorded_at   timestamptz not null default now(),
  unique (bid_id, criterion_id)
);

create table tie_break_decisions (
  id            uuid primary key default gen_random_uuid(),
  authority_id  uuid not null references authorities(id) on delete cascade,
  evaluation_id uuid not null references evaluations(id) on delete cascade,
  rule_applied  text not null,
  outcome       text not null,
  actor_id      uuid not null,
  decided_at    timestamptz not null default now()
);

create table audit_events (
  id            uuid primary key default gen_random_uuid(),
  authority_id  uuid not null references authorities(id) on delete cascade,
  evaluation_id uuid references evaluations(id) on delete cascade,
  actor_id      uuid,
  action        text not null,
  entity        text,
  entity_id     text,
  detail        jsonb,
  created_at    timestamptz not null default now()
);

-- ── append-only audit (E-AC1 equivalent) ───────────────────────────────────────
-- Refused even to the service role. The bidder side proved this makes a tenant permanently
-- undeletable; that is the guarantee working, and it is why erasure is an out-of-product
-- process rather than a feature.
create or replace function audit_append_only() returns trigger
language plpgsql as $$
begin
  raise exception 'audit_events is append-only';
end $$;

create trigger audit_no_update before update on audit_events
  for each row execute function audit_append_only();
create trigger audit_no_delete before delete on audit_events
  for each row execute function audit_append_only();

-- ── RLS ────────────────────────────────────────────────────────────────────────
alter table authorities        enable row level security;
alter table authority_members  enable row level security;
alter table profiles           enable row level security;
alter table evaluations        enable row level security;
alter table criteria           enable row level security;
alter table bids               enable row level security;
alter table bid_responses      enable row level security;
alter table bid_financials     enable row level security;
alter table coi_declarations   enable row level security;
alter table scores             enable row level security;
alter table consensus_marks    enable row level security;
alter table tie_break_decisions enable row level security;
alter table audit_events       enable row level security;

-- Bootstrap policy: a bare user_id comparison. It must NOT call current_authority_id(),
-- which reads this same table — that recursion surfaces as a 42P17 and a 500.
create policy members_self on authority_members for select using (user_id = auth.uid());
create policy profiles_self on profiles for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy authorities_member on authorities for select
  using (id in (select authority_id from authority_members where user_id = auth.uid()));

create policy eval_scope on evaluations for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());
create policy criteria_scope on criteria for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());
create policy bids_scope on bids for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());
create policy responses_scope on bid_responses for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());
create policy coi_scope on coi_declarations for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());
create policy scores_scope on scores for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());
create policy consensus_scope on consensus_marks for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());
create policy tie_scope on tie_break_decisions for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());
create policy audit_read on audit_events for select using (authority_id = current_authority_id());
create policy audit_insert on audit_events for insert with check (authority_id = current_authority_id());

-- THE SEALED-BID POLICY. Two conditions, both required: your authority, AND the evaluation's
-- technical scores are locked. Defence in depth — the handler checks it too, but a forgotten
-- check in some future read path still cannot leak an amount.
create policy financial_sealed on bid_financials for select using (
  authority_id = current_authority_id()
  and exists (
    select 1 from bids b join evaluations e on e.id = b.evaluation_id
    where b.id = bid_financials.bid_id and e.technical_locked_at is not null
  )
);
create policy financial_write on bid_financials for insert
  with check (authority_id = current_authority_id());

create index on evaluations (authority_id, created_at desc);
create index on criteria (evaluation_id, order_index);
create index on bids (evaluation_id);
create index on bid_responses (bid_id);
create index on scores (evaluation_id, bid_id, criterion_id);
create index on audit_events (evaluation_id, created_at desc);
