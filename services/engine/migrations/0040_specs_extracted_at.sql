-- When the schedule's specifications were last read out of the line descriptions.
--
-- NULL means "never read", and that is a different sentence from "read, and these lines state
-- no specification" — the two are opposite messages to a bidder and no column distinguished
-- them. Measured 2026-09-14: 98 line items across five tenders, zero extracted parameters, and
-- a screen that said "NOT ASSESSED" 98 times without being able to say which of the two it
-- meant. Deliberately NOT backfilled: every existing row genuinely has never been read, so
-- NULL is the true value and writing a timestamp would manufacture the claim the column exists
-- to make honestly (docs/known-pitfalls.md — backfilling "the obvious value" can assert the
-- exact lie the column was added to detect).
alter table public.tenders
  add column if not exists specs_extracted_at timestamptz;

comment on column public.tenders.specs_extracted_at is
  'When schedule line specifications were last extracted. NULL = never read, which is not the same as read-and-empty.';
