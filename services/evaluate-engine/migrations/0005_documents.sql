-- N2 — required-document register (F17) and the presence gate (F18).
--
-- The register is the printed checklist an officer keeps beside them, turned into data. It is
-- authored once per tender and then FROZEN at first attribution: changing the checklist while
-- bids are being screened changes who qualifies, retroactively, and nothing in an audit trail
-- would explain why a bidder passed on Tuesday and failed on Wednesday.
--
-- `document_presence` deliberately mirrors the shape of a screening cell. Its third verdict
-- (`needs_review`) exists for the same reason `not_stated` does in screening.py: an extraction
-- or attribution miss must never read as "the bidder did not submit it". That is the single
-- most damaging thing this product could do.

begin;

create table required_documents (
  id             uuid primary key default gen_random_uuid(),
  authority_id   uuid not null references authorities(id) on delete cascade,
  tender_id      uuid not null references tenders(id) on delete cascade,

  label          text not null,
  mandatory      boolean not null default true,
  -- The criterion this requirement came from, when it was derived rather than typed.
  criterion_id   uuid references criteria(id) on delete set null,
  -- Document types that satisfy it, matched against file_attributions.
  accepted_types text[] not null default '{}',
  original_required boolean not null default false,
  notes          text,
  order_index    integer not null default 0,
  created_at     timestamptz not null default now(),

  unique (tender_id, label)
);

create table document_presence (
  requirement_id uuid not null references required_documents(id) on delete cascade,
  bid_id         uuid not null references bids(id) on delete cascade,
  authority_id   uuid not null references authorities(id) on delete cascade,

  -- Only ever written by a human overriding the computed verdict. The computed value is NOT
  -- stored: it is a pure function of the register and the attributed files, and storing it
  -- would let the two disagree the moment a file is re-attributed.
  override_verdict text,          -- present | missing | needs_review
  override_reason  text,
  overridden_by    uuid,
  overridden_at    timestamptz,

  primary key (requirement_id, bid_id)
);

alter table required_documents enable row level security;
alter table document_presence  enable row level security;

create policy req_docs_scope on required_documents for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());
create policy doc_presence_scope on document_presence for all
  using (authority_id = current_authority_id()) with check (authority_id = current_authority_id());

create index on required_documents (tender_id, order_index);
create index on document_presence (authority_id);

commit;
