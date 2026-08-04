-- Which document does "p.4" mean?
--
-- A tender is published as a package — NIT, annexures, a BOQ spreadsheet — and eligibility
-- clauses hide in the annexures as often as in the main notice. Ingest now takes the whole
-- package as ONE tender, which makes a bare page number an unresolvable anchor: three
-- documents all have a page 4. A-AC3 requires the anchor to be resolvable, so the document
-- travels with it.
--
-- Local page, not a running package count. "p.37" is a number printed on nothing the bidder
-- is holding; "Annexure-II.pdf p.4" is a place they can turn to.
--
-- Nullable and unset for every existing row: those tenders came from a single PDF, where the
-- page alone was already resolvable. The UI shows the document only when a tender actually
-- has more than one — a prefix on every row of a single-document tender is noise.

alter table public.criteria      add column if not exists anchor_document text;
alter table public.matrix_rows   add column if not exists anchor_document text;

-- The unmapped backlog (G-FR2) is keyed on (page, sentence) so a re-ingest cannot duplicate
-- it. Once a package can hold two documents, that key silently MERGES the same sentence
-- appearing on page 4 of two annexures — one row where the denominator should count two.
-- The document joins the key to keep the count honest. '' rather than NULL because Postgres
-- treats NULLs as distinct in a unique constraint, which would defeat the re-ingest guard
-- for every single-document tender that exists today.
alter table public.matrix_unmapped
  add column if not exists document text not null default '';

alter table public.matrix_unmapped
  drop constraint if exists matrix_unmapped_workspace_id_tender_id_page_sentence_key;

do $$ begin
  alter table public.matrix_unmapped
    add constraint matrix_unmapped_workspace_tender_doc_page_sentence_key
    unique (workspace_id, tender_id, document, page, sentence);
exception when duplicate_object then null; end $$;

comment on column public.criteria.anchor_document is
  'Document within the tender package this criterion was read from — a filename, or '
  '"file · sheet" for a spreadsheet. NULL on single-document tenders ingested before the '
  'package model. anchor_page is LOCAL to this document.';
