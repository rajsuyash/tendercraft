-- The vendor's annual report, pointed at from the profile.
--
-- Not a new storage path: the document goes through `/api/knowledge/ingest` like every other
-- piece of evidence, so it gets the same text extraction, the same 25 MB ceiling, the same
-- template-placeholder check and the same provenance. This column only records WHICH library
-- document is the annual report, because "the annual report" is a question a bid manager asks
-- and `doc_type = 'financial'` cannot answer — a turnover certificate is financial too.
--
-- Two things read it. A bid manager, who wants the source of the turnover figures on the same
-- screen as the figures. And keyword suggestion, because an annual report describes what the
-- company actually sells in the vocabulary the market uses — which is what a tender title is
-- written in, and what a capability statement usually is not.
--
-- ON DELETE SET NULL rather than CASCADE: deleting the document must not silently delete the
-- vendor profile.

alter table public.vendor_profiles
  add column if not exists annual_report_document_id uuid
    references public.library_documents(id) on delete set null;

comment on column public.vendor_profiles.annual_report_document_id is
  'Which library document is this vendor''s annual report. The document itself lives in the '
  'knowledge base with every other piece of evidence; this is only the pointer.';
