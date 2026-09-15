-- WHAT a stage approval signed off, not merely that someone signed.
--
-- An approval row said "person X signed stage Y of proposal Z at time T" and nothing about
-- what Z contained. Editing a section clears that SECTION's own approval (0017/0031 wired
-- that), but the proposal-level chain survived untouched — so a document could be signed
-- through all its stages, rewritten afterwards, and still export as approved. The watermark
-- exists to stop unreviewed prose reaching a buyer; an approval that does not name its text
-- cannot enforce it.
--
-- The hash is over the ordered section bodies at the moment of signing. `export_service`
-- ignores an approval whose hash no longer matches, so the stage simply becomes incomplete
-- again and the chain asks for a fresh signature.
--
-- NULL means "signed before approvals were bound to content". Deliberately NOT backfilled and
-- deliberately COUNTED rather than invalidated: computing a hash now would assert that those
-- signatures covered today's text, which is exactly the claim the column exists to stop
-- anyone making. Invalidating them instead would silently un-approve every proposal in every
-- workspace. Both are worse than an honest NULL with a named ceiling.
alter table public.proposal_approvals
  add column if not exists content_hash text;

comment on column public.proposal_approvals.content_hash is
  'sha256 over the ordered section bodies at signing time. NULL = signed before content '
  'binding existed, and is counted rather than invalidated — see migration 0043.';
