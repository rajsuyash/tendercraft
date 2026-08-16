-- Close the learning loop at export.
--
-- The answer library (0027) works, and it only ever learned from documents a client uploaded
-- by hand. A proposal produced INSIDE the product — approved section by section, corrected by
-- a bid manager, gated by the export blocker — left the building and taught the system
-- nothing. The absurdity was exact: exporting that same file and re-uploading it through
-- POST /api/past-bids would have mined it perfectly.
--
-- So a harvested proposal becomes a past_bid like any other. Two columns to tell them apart,
-- because they are NOT the same evidence:
--
--   origin='uploaded'   a real submitted document. What the client actually sent a buyer.
--   origin='generated'  harvested from our own export. Only the sections a HUMAN approved or
--                       edited are mined (app/learning.py) — unapproved AI prose is the
--                       model's guess, and mining it would teach the system its own output.
--                       That failure arrives disguised as success: coverage rises, edit rates
--                       fall, and the prose drifts steadily away from how the client writes.
--
-- The unique index is what makes a re-export update rather than duplicate. It is partial
-- because uploaded bids have no proposal_id and there may be many of them.

alter table public.past_bids
  add column if not exists proposal_id uuid references public.proposals(id) on delete set null;

alter table public.past_bids
  add column if not exists origin text not null default 'uploaded';

do $$ begin
  alter table public.past_bids
    add constraint past_bids_origin_check check (origin in ('uploaded', 'generated'));
exception when duplicate_object then null; end $$;

-- Every pre-existing row IS an upload — the harvest path did not exist until now. The column
-- default covers rows written before this migration, but state it: a column only one code
-- path writes renders every older row as the fallback, which is usually the exact bug the
-- column was added to fix (docs/known-pitfalls.md).
update public.past_bids set origin = 'uploaded' where origin is null;

-- workspace_id sits inside the key. The engine writes with the service role and bypasses RLS,
-- so a conflict target that omits the scope column can reassign another workspace's row.
create unique index if not exists past_bids_workspace_proposal_uniq
  on public.past_bids(workspace_id, proposal_id)
  where proposal_id is not null;

comment on column public.past_bids.origin is
  'uploaded = a document the client submitted to a buyer. generated = harvested from our own '
  'export, human-approved sections only. Never merge the two notions: one is evidence of what '
  'an evaluator accepted, the other is evidence of what this client signs their name to.';

comment on column public.past_bids.proposal_id is
  'Set only for origin=generated. Unique per workspace, so re-exporting a proposal re-mines '
  'it in place instead of stacking a near-duplicate answer set under a second bid.';
