-- Watch a submitted bid's progress through evaluation (UML ask 4).
--
-- The ask: "After the technical evaluation of a bid, GeM may require additional documents or
-- clarifications. The system should monitor the tender status and identify such requirements
-- as soon as they are generated on the portal."
--
-- **What this can and cannot do, recorded here because the distinction is the whole feature.**
-- GeM publishes the evaluation LIFECYCLE on the same un-captcha'd surface as the price ladder
-- (Not Evaluated -> Technical Evaluation -> Financial Evaluation -> Bid Award, carried on
-- `b_buyer_status`). So we can tell a seller their bid entered technical evaluation without
-- anyone logging in to their account.
--
-- The TEXT of a clarification or document request lives behind the GeM seller login, which we
-- will not hold (G-1) and will not automate (G-8). This is the alarm clock, not the letter. A
-- feature that implied otherwise would be worse than not having it, because a bidder would
-- stop checking their own portal inbox — and that is the one place the request actually
-- arrives. Every surface rendering this must say so.
--
-- Two columns rather than a new table: a stage is a property of the match, and the transition
-- history that would justify a table has no reader. `notifications_sent` already records what
-- was announced and when, keyed by kind, so 'stage:tech_evaluated' is both the idempotency key
-- and the audit trail.

alter table public.opportunity_matches
  add column if not exists last_stage text;

alter table public.opportunity_matches
  add column if not exists stage_checked_at timestamptz;

-- Every pre-existing row has never been checked, and NULL says exactly that. Backfilling
-- 'not_evaluated' would assert a fact about a bid nobody has looked at — and worse, the first
-- real check would then read as a transition and fire an alert for a bid that had been sitting
-- at technical evaluation for a month (docs/known-pitfalls.md: a column only one path writes).

create index if not exists opportunity_matches_watched_idx
  on public.opportunity_matches(workspace_id) where watched;

comment on column public.opportunity_matches.last_stage is
  'Evaluation stage at the last check. NULL = never checked, which is NOT the same as '
  'not_evaluated: the first check of a NULL row establishes a baseline and must not alert, or '
  'every watched bid announces itself once for no reason.';
