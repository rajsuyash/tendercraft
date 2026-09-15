-- When the OCR pass over this tender's scanned pages finished, and what it recovered.
--
-- WHY. Measured on a real customer corpus (docs/ocr-measurement.md): 52% of 478 pages carried
-- no extractable text, and the unreadable half was almost entirely the BIDDER's own
-- certificates and licences. Those pages are now read by a background pass after the upload
-- has already been answered, so the response the uploader saw can never describe it — the row
-- has to.
--
-- NULL on `ocr_completed_at` means "the pass has not finished", which is a different sentence
-- from "there was nothing to read". The pass stamps even when it recovers nothing, so a zero
-- is an answer rather than an absence; it does NOT stamp when it raised, or when the
-- deployment has no OCR toolchain, because neither of those is a read that happened.
--
-- `ocr_pages_recovered` exists because nothing in this codebase persists page text, so the
-- count cannot be recomputed later from anything. NULL = never ran, 0 = ran and recovered
-- nothing legible, N = N pages that carried no text layer now do.
--
-- Deliberately NOT backfilled, for the same reason as 0040: every existing row genuinely has
-- never had an OCR pass, so NULL is the true value and a timestamp would manufacture the
-- exact claim the column exists to make honestly (docs/known-pitfalls.md — backfilling "the
-- obvious value" can assert the lie the column was added to detect).
alter table public.tenders
  add column if not exists ocr_completed_at timestamptz,
  add column if not exists ocr_pages_recovered integer;

comment on column public.tenders.ocr_completed_at is
  'When the background OCR pass over scanned pages finished. NULL = never ran (or raised, or no OCR toolchain), which is not the same as ran-and-found-nothing.';

comment on column public.tenders.ocr_pages_recovered is
  'Pages that carried no text layer and were recovered by OCR. NULL = the pass never ran; 0 = it ran and recovered nothing.';
