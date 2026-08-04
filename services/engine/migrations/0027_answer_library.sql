-- G-FR3 — the answer library. What the client already wrote, and what it was worth.
--
-- The submitted root cause in the discovery PRD is "poor reuse", and it is a data-model
-- problem, not a discipline problem: prior answers live inside finished Word documents, so the
-- same methodology and the same past-performance narrative are re-typed every bid. A past
-- proposal dropped into `library_documents` today is undifferentiated evidence prose — the
-- retriever hands it to the drafter, which quotes it and attaches a citation. There is no
-- notion of WHICH requirement an answer answered, and no notion of whether the bid won.
--
-- Three tables:
--
--   past_bids      one submitted proposal, with its outcome. Outcome is USER-SET and never
--                  inferred — we cannot see an award notice, and a guessed win is worse than
--                  an honest 'unknown' when it is about to rank what the drafter reuses.
--   answers        requirement -> the answer that satisfied it, mined from a past bid.
--   answer_usages  the receipt (G-AC6). A suggestion that enters a draft without an explicit
--                  human acceptance is a hard zero, and this table is what makes that
--                  testable rather than aspirational: one row per accepted reuse, written by
--                  the single endpoint permitted to insert reused text.
--
-- workspace_id sits INSIDE every unique key. The engine writes with the service role, which
-- bypasses RLS, so a conflict target that omits the scope column can reassign another
-- workspace's row (docs/known-pitfalls.md, learned the hard way here).

do $$ begin
  -- 'unknown' is the default and the honest answer. Most bidders do not learn why they lost.
  create type public.bid_outcome as enum ('won', 'lost', 'unknown');
exception when duplicate_object then null; end $$;

create table if not exists public.past_bids (
  id                 uuid primary key default gen_random_uuid(),
  workspace_id       uuid not null references public.workspaces(id) on delete cascade,
  name               text not null,
  authority          text,
  tender_number      text,
  submitted_on       date,
  outcome            public.bid_outcome not null default 'unknown',
  -- The source document stays in the library too, so existing retrieval keeps working
  -- unchanged and a mined answer can always be traced back to the page it came from.
  source_document_id uuid references public.library_documents(id) on delete set null,
  uploaded_by        uuid,
  created_at         timestamptz not null default now()
);
create index if not exists past_bids_workspace_idx on public.past_bids(workspace_id);

create table if not exists public.answers (
  id               uuid primary key default gen_random_uuid(),
  workspace_id     uuid not null references public.workspaces(id) on delete cascade,
  past_bid_id      uuid not null references public.past_bids(id) on delete cascade,
  requirement_text text not null,
  answer_text      text not null,
  -- Semantic section key from app/sections.py::SECTION_SPECS where the mining recognised one.
  section_key      text,
  category         text,
  -- How the pair was found: 'heading' | 'table' | 'model'. Deterministic provenance for a
  -- suggestion the user is being asked to trust.
  mined_by         text not null default 'heading',
  created_at       timestamptz not null default now(),
  -- Re-mining the same bid must update rather than duplicate.
  unique (workspace_id, past_bid_id, requirement_text)
);
create index if not exists answers_workspace_idx on public.answers(workspace_id);
create index if not exists answers_bid_idx       on public.answers(past_bid_id);

create table if not exists public.answer_usages (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  answer_id    uuid not null references public.answers(id) on delete cascade,
  proposal_id  uuid references public.proposals(id) on delete cascade,
  -- Where it landed: a section key, or a criterion id. One column, because a usage is one
  -- place and two nullable foreign keys would let a row claim to be both.
  target       text not null,
  actor        uuid,
  accepted_at  timestamptz not null default now()
);
create index if not exists answer_usages_workspace_idx on public.answer_usages(workspace_id);
create index if not exists answer_usages_answer_idx    on public.answer_usages(answer_id);

alter table public.past_bids     enable row level security;
alter table public.answers       enable row level security;
alter table public.answer_usages enable row level security;

drop policy if exists past_bids_workspace_all on public.past_bids;
create policy past_bids_workspace_all on public.past_bids for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

drop policy if exists answers_workspace_all on public.answers;
create policy answers_workspace_all on public.answers for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

drop policy if exists answer_usages_workspace_all on public.answer_usages;
create policy answer_usages_workspace_all on public.answer_usages for all
  using (workspace_id = public.current_workspace_id())
  with check (workspace_id = public.current_workspace_id());

comment on table public.answers is
  'G-FR3. Requirement -> the answer that satisfied it, mined from a past bid. Suggested with '
  'provenance and never inserted into a draft without an explicit acceptance (G-AC6).';

comment on column public.past_bids.outcome is
  'User-set, never inferred. It ranks which prior answers are suggested first, so a guessed '
  'win would quietly steer every future proposal.';
