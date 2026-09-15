-- Which pages of the uploaded package could not be read.
--
-- The list was computed at ingest (`app/ingest.py` — every page under MIN_CHARS_PER_PAGE) and
-- travelled back in the HTTP response only. Nothing persisted it, and page text is never
-- stored, so after the upload screen closed there was no record anywhere that part of the
-- tender had never been read. `ready_to_generate` could be true with a third of the package
-- unread; the readiness meter had no parameter that could see it.
--
-- Stored as the human labels ("ATC.pdf p.14") rather than a count, because "17 pages unread"
-- is not actionable and "ATC.pdf p.14, p.15" is — the same reasoning that made the ingest
-- response name them instead of counting them.
--
-- Not backfilled: for every existing tender the list is genuinely unknown, and an empty array
-- would assert the package was fully readable, which is the claim this column exists to make
-- honestly. NULL means "never recorded"; [] means "recorded, and every page was readable".
alter table public.tenders
  add column if not exists illegible_pages jsonb;

comment on column public.tenders.illegible_pages is
  'Human labels of pages with no readable text at ingest. NULL = never recorded (pre-0044); '
  '[] = recorded and every page was readable. OCR may later recover some — see '
  'ocr_pages_recovered.';
