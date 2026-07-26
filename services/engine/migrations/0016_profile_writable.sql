-- Make the vendor profile writable, and give it a legal name.
--
-- Two findings from the bidder-journey walk:
--   * "Update profile" was a dead button and the ONLY exit from an eligibility gap. The
--     readiness page instructs "update it there and Re-match"; there was nothing to update.
--   * The proposal took the bidder's company name from PROSE in an uploaded document — a
--     declaration still containing [Insert Designation] — and wrote "Merdian Technology"
--     into a government submission, with a citation attached. The legal name must be
--     structured data that transcludes, never something a model reads out of a file.
-- Idempotent.

alter table public.vendor_profiles add column if not exists legal_name text;

-- Backfill from the workspace name: for a direct bidder they are the same thing, and it is
-- strictly better than the misspelling currently reaching the document.
update public.vendor_profiles v
   set legal_name = w.name
  from public.workspaces w
 where w.id = v.workspace_id and v.legal_name is null;
