-- Human editing of proposal sections.
--
-- The proposal page had ZERO editable fields. A bidder who spotted a wrong company name or
-- an overstated claim had no way to correct it, so the only options were to submit text
-- they knew was wrong or to rewrite the document by hand — which removes the reason to use
-- the product at all.
--
-- Provenance matters more than the edit: once a human rewrites a sentence it is no longer
-- AI-authored, and the document must say so rather than keep an "AI DRAFT" mark that is now
-- untrue. Approval is still required — editing is authorship, not sign-off. Idempotent.

alter table public.proposal_sections add column if not exists edited_by uuid;
alter table public.proposal_sections add column if not exists edited_at timestamptz;
