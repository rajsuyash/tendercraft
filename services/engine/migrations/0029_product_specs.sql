-- Module H — what the bidder can make, what the tender asks for, and whether those meet.
--
-- Prompted by design-partner feedback (docs/feedback/usha-martin.md, asks 2 and 3): a
-- manufacturer's bid is won on "can we supply this exact item, and is it already listed",
-- and the product had no way to represent either question. `vendor_profiles` holds money,
-- identity, certificates and past projects; the only thing it knows about what a bidder MAKES
-- is a free-text capability statement that ranks the opportunity feed and reaches no verdict.
--
-- Three tables:
--
--   product_specs      what we can make (spec_kind='envelope') and what we have listed
--                      (spec_kind='catalogue'). Same shape on purpose — see below.
--   tender_line_items  one schedule line / BOQ row / technical criterion, with its anchor.
--   spec_parameters    the only place a typed parameter ever lives, on either side.
--
-- WHY A POINT AND A RANGE ARE THE SAME ROW. A required "20 mm" is num_min = num_max = 20; a
-- manufacturing envelope of 6-60 mm is 6..60; "MBL >= 200 kN" is (200, null). One interval
-- intersection answers every phrasing, so the comparator has no operator column and no branch
-- per wording. A catalogue item is therefore an envelope whose intervals happen to be points,
-- which is why both live in one table with one RLS policy and one editor.
--
-- WHY TYPED-EAV AND NOT COLUMNS. Fixed columns (diameter_mm, construction, core_type...) fit
-- exactly one customer, are ~80% NULL on that customer, and force NULL to mean both "not
-- applicable" and "unknown" — the one distinction this comparator must never blur, because
-- confusing them turns "we could not read it" into "we cannot make it" and loses a winnable
-- bid. They also fit UML alone poorly: MIG welding wire shares almost no parameter with the
-- eight rope standards beside it.
--
-- WHY NOT JSONB. app/deterministic/ is CI-gated at 100% branch coverage. A jsonb reader is an
-- untestable branch tree by construction, and its first malformed write is accepted silently
-- and surfaces months later as "the feature does not work" with no error anywhere. The CHECK
-- constraints below put shape validation in Postgres, which is the one layer a service-role
-- write cannot bypass.
--
-- The canonical parameter registry (key -> kind, unit, synonyms) lives in code, at
-- app/deterministic/spec_params.py. A dict is a table without a migration; move it here when a
-- customer needs to add a parameter without a deploy.
--
-- workspace_id sits INSIDE every unique key. The engine writes with the service role, which
-- bypasses RLS, so a conflict target that omits the scope column can reassign another
-- workspace's row (docs/known-pitfalls.md, learned the hard way on 0027).

do $$ begin
  create type public.spec_kind as enum ('envelope', 'catalogue');
exception when duplicate_object then null; end $$;

do $$ begin
  -- Two kinds, deliberately. Galvanisation is modelled as an enum ('galvanised' /
  -- 'ungalvanised') rather than a boolean, so "we do both" is a two-value allowed set instead
  -- of a third meaning for NULL. Every kind added here is a branch the 100%-coverage gate has
  -- to carry, so it is added only when a real requirement cannot be expressed without it.
  create type public.spec_param_kind as enum ('numeric', 'enum');
exception when duplicate_object then null; end $$;

create table if not exists public.product_specs (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null references public.workspaces(id) on delete cascade,
  spec_kind           public.spec_kind not null,
  label               text not null,
  -- 'IS 2266', 'API Spec 9A'. Compared as an ordinary enum parameter when a tender names one;
  -- held here too because it is how a human recognises the row.
  standard_ref        text,
  -- A catalogue item records which envelope it was created from. That is what makes a
  -- "can be created" answer actionable rather than merely true.
  parent_envelope_id  uuid references public.product_specs(id) on delete set null,
  -- The seller's own GeM item id, typed or pasted by them. We never read GeM to obtain or
  -- verify it: G-1 forbids portal credentials and G-8 forbids authenticated acquisition, so
  -- "published" means "the catalogue YOU recorded with us" and every surface must say so.
  gem_catalogue_id    text,
  created_by          uuid,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  constraint product_specs_envelope_has_no_parent
    check (spec_kind = 'catalogue' or parent_envelope_id is null),
  unique (workspace_id, spec_kind, label)
);
create index if not exists product_specs_workspace_idx on public.product_specs(workspace_id);
create index if not exists product_specs_parent_idx    on public.product_specs(parent_envelope_id);

create table if not exists public.tender_line_items (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null references public.workspaces(id) on delete cascade,
  tender_id           uuid not null references public.tenders(id) on delete cascade,
  schedule_ref        text,
  item_ref            text,
  description         text not null,
  quantity            numeric,
  uom                 text,
  -- Cite-or-flag applies to a line item exactly as it applies to a criterion: every row points
  -- at the bytes it came from. A BOQ row anchors to (document, row); a line item derived from
  -- prose anchors to the criterion it came from.
  anchor_document     text,
  anchor_page         integer,
  anchor_row          integer,
  source_criterion_id uuid references public.criteria(id) on delete cascade,
  confirmed           boolean not null default false,
  created_at          timestamptz not null default now(),
  constraint tender_line_items_has_a_source
    check (anchor_row is not null or source_criterion_id is not null)
);
create index if not exists tender_line_items_workspace_idx on public.tender_line_items(workspace_id);
create index if not exists tender_line_items_tender_idx    on public.tender_line_items(tender_id);

-- Re-ingesting a package must update rather than duplicate, and a line item has two possible
-- identities. Partial indexes rather than one wide unique constraint because Postgres treats
-- NULLs as distinct: `unique (workspace_id, tender_id, anchor_document, anchor_row)` would
-- happily accept the same criterion-derived row a hundred times.
create unique index if not exists tender_line_items_boq_key
  on public.tender_line_items(workspace_id, tender_id, anchor_document, anchor_row)
  where anchor_row is not null;
create unique index if not exists tender_line_items_criterion_key
  on public.tender_line_items(workspace_id, source_criterion_id)
  where source_criterion_id is not null;

create table if not exists public.spec_parameters (
  id              uuid primary key default gen_random_uuid(),
  workspace_id    uuid not null references public.workspaces(id) on delete cascade,
  -- Exactly one owner. Two nullable foreign keys would let a row claim to be both a capability
  -- and a requirement, which is the one thing the comparator reads them to tell apart.
  product_spec_id uuid references public.product_specs(id) on delete cascade,
  line_item_id    uuid references public.tender_line_items(id) on delete cascade,
  param_key       text not null,
  kind            public.spec_param_kind not null,
  -- Canonical unit for the key where one exists ('mm', 'kN', 'N/mm2'), or the unit as stated.
  -- Both sides normalise before comparison; an unconvertible pair is UNKNOWN, never a failure.
  unit            text,
  num_min         numeric,
  num_max         numeric,
  allowed_values  text[] not null default '{}',
  -- The substring this value was read from. Cite-or-flag: a parameter with no visible source
  -- is an assertion, and this product does not make those.
  raw_text        text not null default '',
  confidence      numeric check (confidence is null or (confidence >= 0 and confidence <= 1)),
  confirmed       boolean not null default false,
  created_at      timestamptz not null default now(),
  constraint spec_parameters_one_owner
    check (num_nonnulls(product_spec_id, line_item_id) = 1),
  -- A numeric with neither bound and an enum with no values are both unreadable rows that
  -- would silently become UNKNOWN forever. Refuse them at write time instead.
  constraint spec_parameters_numeric_is_bounded
    check (kind <> 'numeric' or (num_min is not null or num_max is not null)),
  constraint spec_parameters_numeric_range_ordered
    check (num_min is null or num_max is null or num_min <= num_max),
  constraint spec_parameters_enum_has_values
    check (kind <> 'enum' or cardinality(allowed_values) > 0)
);
create index if not exists spec_parameters_workspace_idx on public.spec_parameters(workspace_id);
create index if not exists spec_parameters_spec_idx      on public.spec_parameters(product_spec_id);
create index if not exists spec_parameters_line_idx      on public.spec_parameters(line_item_id);

-- Same NULL-distinctness trap as the line items above, and the consequence here is worse: a
-- duplicated parameter means the comparator reads one of two contradictory values, chosen by
-- row order.
create unique index if not exists spec_parameters_spec_key
  on public.spec_parameters(workspace_id, product_spec_id, param_key)
  where product_spec_id is not null;
create unique index if not exists spec_parameters_line_key
  on public.spec_parameters(workspace_id, line_item_id, param_key)
  where line_item_id is not null;

alter table public.product_specs     enable row level security;
alter table public.tender_line_items enable row level security;
alter table public.spec_parameters   enable row level security;

drop policy if exists product_specs_workspace_all on public.product_specs;
create policy product_specs_workspace_all on public.product_specs for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

drop policy if exists tender_line_items_workspace_all on public.tender_line_items;
create policy tender_line_items_workspace_all on public.tender_line_items for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

drop policy if exists spec_parameters_workspace_all on public.spec_parameters;
create policy spec_parameters_workspace_all on public.spec_parameters for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

comment on table public.product_specs is
  'Module H. spec_kind=envelope is what the bidder can manufacture; spec_kind=catalogue is '
  'what they have listed on GeM. Same shape, because a catalogue item is an envelope whose '
  'intervals are points.';

comment on column public.product_specs.gem_catalogue_id is
  'Bidder-supplied. We never read GeM to obtain or verify it (G-1/G-8), so any UI showing a '
  'published state must say it reflects the catalogue the bidder recorded, not the portal.';

comment on table public.spec_parameters is
  'One typed parameter on one side of the comparison. num_min=num_max is a point value; a NULL '
  'bound is unbounded. A parameter that cannot be read is ABSENT, and the comparator reports '
  'unknown — never a deviation, because a false "we cannot make this" loses a winnable bid.';
