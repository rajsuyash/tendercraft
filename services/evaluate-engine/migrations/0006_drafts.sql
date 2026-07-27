-- N4 — authoring a tender before it is published (F22–F26, TP1).
--
-- Everything the base product does begins at "upload the RFP that was published". This is the
-- step before that: the officer writes the tender here, the regulatory checks run against it as
-- they type, named reviewers sign it off, and publishing creates the tender WITH its framework
-- already populated. That last part is the whole point — the criteria are never re-keyed, so
-- the ambiguity cannot drift between the published document and the thing bids are scored on.
--
-- `draft_criteria` deliberately mirrors `criteria` rather than sharing it. A draft criterion is
-- editable and means nothing; a tender criterion governs a live public procurement and freezes
-- at framework lock. One table for both would put a published tender one UPDATE away from
-- changing what bidders were told.

begin;

create table drafts (
  id             uuid primary key default gen_random_uuid(),
  authority_id   uuid not null references authorities(id) on delete cascade,

  title          text not null,
  tender_number  text,
  category       text not null default 'goods',   -- goods | works | services
  scope          text,

  estimated_value        numeric(16,2),
  estimated_annual_value numeric(16,2),
  submission_window_days integer,
  bid_structure          text default 'two_envelope',
  emd_amount             numeric(16,2),
  emd_exemption_stated   boolean not null default false,
  pre_bid_meeting_at     date,
  pre_bid_days_before_deadline integer,

  technical_weight  integer not null default 70,
  financial_weight  integer not null default 30,
  qualifying_marks  integer,
  quorum            integer not null default 3,

  state          text not null default 'drafting',   -- drafting | in_review | published
  -- Stamped at publication so a tender can be re-checked years later against the rules that
  -- actually applied to it, not whichever rulepack is current when the auditor asks.
  rulepack_version text,
  published_tender_id uuid references tenders(id) on delete set null,
  published_at   timestamptz,

  created_by     uuid,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create table draft_criteria (
  id             uuid primary key default gen_random_uuid(),
  authority_id   uuid not null references authorities(id) on delete cascade,
  draft_id       uuid not null references drafts(id) on delete cascade,

  kind           text not null default 'pq',       -- pq | technical
  text           text not null,
  max_marks      integer not null default 0,
  evaluation_method text,

  compare_kind   text default 'qualitative',
  compare_op     text,
  compare_value  text,
  -- Names the quantity this criterion constrains, so a ratio rule knows which criteria are its
  -- business. Without it every ratio rule fires on every numeric criterion in the tender.
  compare_field  text,

  order_index    integer not null default 0
);

create table draft_reviews (
  id             uuid primary key default gen_random_uuid(),
  authority_id   uuid not null references authorities(id) on delete cascade,
  draft_id       uuid not null references drafts(id) on delete cascade,

  reviewer_id    uuid,
  reviewer_role  text not null,          -- legal | finance | technical | procurement
  comment        text,
  signed_off_at  timestamptz,
  -- A sign-off on a document that then changed is not a sign-off (F25-AC4).
  invalidated_at timestamptz,
  created_at     timestamptz not null default now(),

  unique (draft_id, reviewer_role)
);

create table draft_finding_dismissals (
  draft_id       uuid not null references drafts(id) on delete cascade,
  authority_id   uuid not null references authorities(id) on delete cascade,
  rule_id        text not null,
  target_id      uuid,
  reason         text not null,          -- an override with no "why" is not an explanation
  dismissed_by   uuid,
  dismissed_at   timestamptz not null default now(),
  primary key (draft_id, rule_id, target_id)
);

alter table drafts                   enable row level security;
alter table draft_criteria           enable row level security;
alter table draft_reviews            enable row level security;
alter table draft_finding_dismissals enable row level security;

create policy drafts_scope on drafts for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());
create policy draft_criteria_scope on draft_criteria for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());
create policy draft_reviews_scope on draft_reviews for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());
create policy draft_dismissals_scope on draft_finding_dismissals for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());

create index on drafts (authority_id, created_at desc);
create index on draft_criteria (draft_id, order_index);
create index on draft_reviews (draft_id);

commit;
