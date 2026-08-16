-- Keep what the model wrote, so we can learn from what the human changed.
--
-- `edit_section` overwrote body_md in place, and the AI original was gone. That diff is the
-- highest-value signal this product ever generates: a labelled example of THIS client's
-- standard, produced free, at the exact moment a bid manager cared enough to retype a
-- paragraph. Every one of them was thrown away.
--
-- One nullable column recovers it. It is written on the FIRST edit only — a second edit is a
-- human refining their own prose, not correcting the model, and letting it overwrite would
-- turn the delta into noise that shrinks toward zero the more carefully someone works.
--
-- Backfill: for rows nobody has edited, the current body IS the model's original, so copy it.
-- For rows already edited the original is unrecoverable, and NULL says so. Guessing here
-- would manufacture edit deltas of zero for exactly the sections that were rewritten most —
-- the opposite of the truth, in the metric built to measure whether the system is improving.

alter table public.proposal_sections add column if not exists original_md text;

update public.proposal_sections
   set original_md = body_md
 where original_md is null
   and edited_by is null
   and body_md <> '';

comment on column public.proposal_sections.original_md is
  'What the drafter wrote, before any human edit. Written once, on the first edit. NULL means '
  'the original is unknown (pre-0031 rows already edited) — never that nothing changed.';
