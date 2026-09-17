-- Whether the scheduled sweep recomputes this workspace's opportunity feed.
--
-- The measurement that forced it (2026-09-17): the org hit 12.89 GB against a 5.5 GB Free
-- egress quota and Supabase blocked the API. Of the six workspaces that have a member — the
-- predicate migration 0011's access rule gave us, and the one the 2026-09-14 fix filters the
-- sweep on — FIVE are demo fixtures (Meridian Infotech, Sterling Logistics, PwC India, a
-- second Usha Martin, Groupe Convergence Conseil). One is the customer. Each of the six costs
-- a full corpus read on every sweep: ~1.16 MB for an Indian workspace, ~4.66 MB for the
-- French one, three times a day. Having a member made them reachable; it never made them
-- wanted.
--
-- "Has a member" is the strongest predicate the product's own access rule can supply, and it
-- has now been pushed as far as it goes. Anything beyond it is a guess about which workspaces
-- matter, and this repo has written down twice why those guesses are forbidden here: a name
-- pattern like "Test" or "Dup" is a heuristic about our own fixtures that a real customer
-- trips over by naming a workspace badly, and a workspace silently dropped from the fan-out is
-- a feed that stops updating with nothing anywhere saying so (ET-7 — the exact failure the
-- sweep exists to prevent). So the predicate is not cleverer. It is a switch, and a human
-- throws it: WHICH WORKSPACES TO TURN OFF IS THE OWNER'S DECISION, made in Settings.
--
-- `not null default true` IS the backfill, and it is a true statement about every existing
-- row rather than a convenient one: every workspace in this database today is swept, so
-- recording every one of them as enabled changes nothing on deploy. That is the point —
-- behaviour must be byte-identical until somebody flips a toggle, because a migration that
-- silently switches feeds off is the ET-7 failure arriving through the fix for it. The default
-- also covers the memberless test debris, harmlessly: those rows are already dropped from the
-- fan-out by `_workspaces_with_members`, so their flag is never read.
--
-- Scope is the SCHEDULED sweep only. A human who opens the feed and presses Refresh still gets
-- a recompute (`POST /api/opportunities/refresh`) — turning this off buys back the unattended
-- three-times-a-day cost, it does not take the feature away from someone standing in front of
-- it.
alter table public.workspaces
  add column if not exists discovery_enabled boolean not null default true;

comment on column public.workspaces.discovery_enabled is
  'False = the scheduled sweep skips this workspace''s opportunity recompute. Existing matches '
  'stay and a manual refresh still works. Set by a workspace admin in Settings (audited as '
  'discovery_enabled_changed); never inferred from a name or a fixture heuristic. Default true '
  'so migration 0047 preserved the pre-0047 fan-out exactly.';
