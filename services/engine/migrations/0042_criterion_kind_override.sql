-- What a bidder is supposed to DO about a requirement — the human's correction to it.
--
-- The kind itself is NOT stored. It is a pure function of `verbatim_text`, `category` and
-- `requirement_level`, all already on the row, so `app/deterministic/requirement_kind.py`
-- computes it at read time. That means improving a rule reclassifies every existing tender on
-- the next deploy instead of needing a data migration, and there is never a half-classified
-- corpus to reason about.
--
-- The override is the one part that cannot be recomputed, so it is the one part with a column.
--
-- Deliberately NOT backfilled, on the same reasoning as 0040/0041: NULL is the TRUE value for
-- every existing row, because no human has overridden anything. Writing a value would
-- manufacture exactly the claim this column exists to record honestly.
--
-- Why this exists at all: measured on GEM/2026/B/7876746 on 2026-09-15, eighteen criteria were
-- mandatory and therefore voted on the bid/no-bid card. Four were post-award inspection duties,
-- four were quoting instructions, four were blank declaration forms, three were rules about how
-- you may bid, and none was a pre-bid eligibility gate. The card read NO-BID on a tender
-- squarely inside the bidder's core product line.
do $$ begin
  create type public.criterion_kind as enum
    ('gate','obligation','instruction','form','spec');
exception when duplicate_object then null; end $$;

alter table public.criteria
  add column if not exists kind_override public.criterion_kind;

comment on column public.criteria.kind_override is
  'Human correction to the computed requirement kind. NULL = not overridden, which is not the '
  'same as any particular kind. The kind itself is computed at read time and never stored.';
