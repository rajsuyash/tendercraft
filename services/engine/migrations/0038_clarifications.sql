-- Pre-bid clarifications — UML ask 2, step 2 of their process flow.
--
-- Module H already computed this and dropped it: `spec_match.catalogue_state` returns
-- `action_parameters`, whose own definition calls it "the pre-bid clarification trigger", and
-- the schedule screen renders the word "Clarify:" beside the parameter keys with nowhere to go.
-- These rows are where the question goes, what the buyer said back, and what that answer did to
-- the verdict.
--
-- WHY THIS IS A TABLE AND NOT A DERIVED VIEW. The queries themselves are pure derivation —
-- `deterministic/clarification.build_queries` recomputes them from the schedule every time. The
-- buyer's ANSWER is not derivable from anything, arrives once, and is the only artefact here
-- that cannot be reconstructed. That asymmetry decides every rule below.
--
-- ONE ROW PER (TENDER, PARAMETER), which is exactly how the pack folds: one diameter deviating
-- across nine schedule lines is one question. `line_ids` keeps the nine references so an answer
-- applies back to every line it settles.
--
-- NEVER DELETE-AND-REBUILD ON RE-ASSESSMENT. Re-reading a corrigendum re-derives the pack, and
-- the obvious implementation — clear the tender's rows, insert the new ones — destroys the
-- buyer's replies, which is the one column no re-run can recover. Same failure the answer
-- library hit when a re-harvest cascaded `answer_usages` away (docs/known-pitfalls.md). Upsert
-- on the stable key instead; `param_key` comes from a closed registry, so it does not move.
--
-- DERIVED COLUMNS REFRESH ONLY WHILE status = 'draft'. Once a question has been sent it stops
-- being a derived value and becomes a record of what was actually put in front of a public
-- buyer. Re-running the assessment must not rewrite the text of a question already asked — the
-- trigger below refuses it rather than trusting every future write path to remember.

do $$ begin
  create type public.clarification_status as enum (
    'draft',      -- derived, not yet asked; safe to refresh
    'sent',       -- the bidder posted it on the portal. WE never post (G-1)
    'answered',   -- the buyer replied
    'withdrawn'   -- the bidder decided not to ask
  );
exception when duplicate_object then null; end $$;

do $$ begin
  -- How the answer reached us. 'portal' is the bidder reading GeM and typing it in; 'email' is
  -- the forwarded-mail path (0035). Neither is us reading the portal logged in.
  create type public.clarification_answer_source as enum ('portal', 'email', 'manual');
exception when duplicate_object then null; end $$;

create table if not exists public.tender_clarifications (
  id                uuid primary key default gen_random_uuid(),
  workspace_id      uuid not null references public.workspaces(id) on delete cascade,
  tender_id         uuid not null references public.tenders(id)    on delete cascade,

  -- From spec_params.REGISTRY. Not an FK because the registry is code (see 0029's note).
  param_key         text not null,
  -- Mirrors deterministic/clarification.QueryKind. A UI array mirroring a server enum WILL
  -- drift (docs/known-pitfalls.md), so both ends say so in a comment and the values match.
  kind              text not null check (kind in ('relaxation', 'confirmation')),

  -- What gets sent. Templated deterministically; no model writes it, and it never contains the
  -- bidder's own capability — GeM publishes a buyer's answers to every bidder on the tender.
  query_text        text not null check (length(btrim(query_text)) > 0),
  required_display  text not null default '',
  -- Workspace-internal: why this question exists, in the comparator's words. Never sent.
  rationale         text not null default '',
  line_ids          uuid[] not null default '{}',

  status            public.clarification_status not null default 'draft',
  sent_at           timestamptz,
  answered_at       timestamptz,
  answer_text       text,
  answer_source     public.clarification_answer_source,

  -- Bare uuid, matching 0027/0029: no FK into the auth schema, which the ephemeral CI stack
  -- rebuilds from these migrations alone.
  created_by        uuid,
  answered_by       uuid,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),

  -- A status is a claim about something that happened; it needs the thing that happened.
  constraint clarifications_sent_has_a_time
    check (status not in ('sent', 'answered') or sent_at is not null),
  constraint clarifications_answered_has_an_answer
    check (status <> 'answered'
           or (answered_at is not null and length(btrim(coalesce(answer_text, ''))) > 0)),
  -- An answer with no stated source is an unattributed claim about what a public buyer said.
  constraint clarifications_answer_has_a_source
    check (answer_text is null or answer_source is not null),

  -- workspace_id INSIDE the key: the engine writes with the service role and bypasses RLS, so a
  -- conflict target omitting the scope column can reassign another workspace's row (0027).
  unique (workspace_id, tender_id, param_key)
);

create index if not exists tender_clarifications_workspace_idx
  on public.tender_clarifications(workspace_id);
create index if not exists tender_clarifications_tender_idx
  on public.tender_clarifications(workspace_id, tender_id, status);

-- The refresh guard. `build_queries` re-derives the whole pack on every assessment, and the
-- upsert that stores it must be unable to rewrite a question already asked — including through
-- the service role, which is the only writer that reaches this table today and the one that
-- bypasses every other protection.
create or replace function public.tender_clarifications_freeze_sent()
returns trigger language plpgsql as $$
begin
  if old.status <> 'draft' then
    if new.query_text is distinct from old.query_text then
      raise exception 'a clarification already % cannot have its text rewritten', old.status
        using errcode = 'check_violation';
    end if;
    if new.kind is distinct from old.kind then
      raise exception 'a clarification already % cannot change kind', old.status
        using errcode = 'check_violation';
    end if;
  end if;
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists tender_clarifications_freeze on public.tender_clarifications;
create trigger tender_clarifications_freeze
  before update on public.tender_clarifications
  for each row execute function public.tender_clarifications_freeze_sent();

alter table public.tender_clarifications enable row level security;

drop policy if exists tender_clarifications_workspace_all on public.tender_clarifications;
create policy tender_clarifications_workspace_all on public.tender_clarifications for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

comment on table public.tender_clarifications is
  'Module H / UML ask 2. One pre-bid question per (tender, parameter). The query text is '
  'derived and refreshable while draft; the buyer''s answer is not derivable and is never '
  'rebuilt. We never post to GeM (G-1) — status=sent records that the BIDDER posted it.';

comment on column public.tender_clarifications.rationale is
  'Workspace-internal. Holds the comparator''s reason, which names the bidder''s own capability '
  'range — and GeM publishes a buyer''s clarification answers to every bidder on the tender, so '
  'this column must never be rendered into query_text or any outbound surface.';

comment on column public.tender_clarifications.line_ids is
  'Every schedule line this one question covers. The pack folds by parameter, so an answer here '
  'settles all of them at once.';
