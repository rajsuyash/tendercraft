-- N1 — bulk intake (F14), attribution + triage (F15), format normalisation (F16).
--
-- Two tables. `bid_files` is every file received, whatever archive it arrived in. It exists
-- BEFORE we know which bidder sent it, which is the whole point: today the officer opens each
-- file to find that out, and the file has nowhere to live until they do.
--
-- `file_attributions` keeps the model's proposal and the human's confirmation in SEPARATE
-- columns. A confirmation never overwrites a proposal. The audit needs both, and so does any
-- honest answer to "how often is the model wrong?" — which is a question a procurement auditor
-- is entitled to ask and we should not have to guess at.
--
-- NOTE what is deliberately absent: any money column. Financial content extracted from a file
-- goes to bid_financials, which carries the row-level seal keyed on technical_locked_at. A
-- money-valued column here would bypass that seal without failing a single existing test —
-- tools/check-throughput-guardrails.sh greps migrations for exactly this (T-1).

begin;

create table bid_files (
  id             uuid primary key default gen_random_uuid(),
  authority_id   uuid not null references authorities(id) on delete cascade,
  tender_id      uuid not null references tenders(id) on delete cascade,

  filename       text not null,
  sha256         text not null,
  mime           text,
  byte_size      bigint,
  source_archive text,                    -- the ZIP it came out of, null if uploaded directly

  page_count     integer,
  status         text not null default 'received',
    -- received | normalising | extracted | failed
  error_code     text,                    -- named, never a stack trace (F14-AC4)
  error_detail   text,
  ocr_pages      integer[] not null default '{}',
  illegible_pages integer[] not null default '{}',

  created_at     timestamptz not null default now(),

  -- The idempotency guarantee behind F14-AC3: re-uploading the same archive re-uploads the
  -- same bytes, and the same bytes are the same file. Content-hashed, not filename-hashed,
  -- because portal downloads arrive as bid_1.pdf twelve times over.
  unique (tender_id, sha256)
);

create table file_attributions (
  file_id        uuid primary key references bid_files(id) on delete cascade,
  authority_id   uuid not null references authorities(id) on delete cascade,

  -- what the model thinks
  proposed_bidder_name  text,
  proposed_bid_id       uuid references bids(id) on delete set null,
  proposed_document_type text,
  proposed_envelope     text,             -- technical | financial | unknown
  confidence            numeric(4,3),
  evidence_text         text,
  anchor_page           integer,

  -- what a human decided. Never overwrites the columns above.
  confirmed_bid_id      uuid references bids(id) on delete set null,
  confirmed_document_type text,
  confirmed_envelope    text,
  confirmed_by          uuid,
  confirmed_at          timestamptz,

  updated_at            timestamptz not null default now()
);

alter table bid_files         enable row level security;
alter table file_attributions enable row level security;

create policy bid_files_scope on bid_files for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());
create policy file_attr_scope on file_attributions for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());

create index on bid_files (tender_id, created_at desc);
create index on bid_files (tender_id, status);
create index on file_attributions (authority_id);

commit;
