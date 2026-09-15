-- Which sections THIS tender's proposal needs, and which ones stopped being needed.
--
-- A fixed seventeen-section IT-services packet was applied to every tender, wire-rope supply
-- bids included, which is why most of that document was unusable. `SECTION_SPECS` is now the
-- catalogue and the outline records which entries a tender selected, with the row that
-- selected each one — cite-or-flag applied to structure, so a screen can say "Team
-- Composition is here because of the CV format at p.31" and equally "Training is absent
-- because nothing in this tender asks for it".
--
-- `included` is the anti-orphaning half and it is the easy one to forget. A re-derive that
-- drops a section sets it false; nothing is ever DELETED, so `original_md`, `edited_by`,
-- `approved_at` and every `answer_usages` receipt survive. Deleting instead would destroy
-- the G-AC6 acceptance receipts, which are the only record proving no suggestion entered a
-- draft unaccepted — the same reason a re-harvest upserts rather than rebuilding `answers`.
--
-- `default true` is correct rather than convenient here, and it is the one column in this
-- chain that IS backfilled by its default: every existing section row was generated under
-- the fixed outline and was, in fact, included. That is a true statement about those rows,
-- unlike the NULLs in 0040-0045.
--
-- `proposals.outline` is NULL for every proposal generated before this existed. NULL means
-- "never derived", which is the true value, and the code stamps those `source: "legacy"`
-- with today's catalogue on first touch so an old proposal keeps behaving identically until
-- a human asks for a re-derive.
alter table public.proposals
  add column if not exists outline jsonb;

alter table public.proposal_sections
  add column if not exists included boolean not null default true;

comment on column public.proposals.outline is
  'Derived section list: which catalogue entries this tender selected and why. NULL = never '
  'derived (generated before migration 0046).';
comment on column public.proposal_sections.included is
  'False = a re-derive found this tender no longer needs the section. Never deleted, so the '
  'human edit, the approval and the reuse receipts survive.';
