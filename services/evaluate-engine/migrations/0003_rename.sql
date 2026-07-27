-- Rename evaluations -> tenders, evaluation_id -> tender_id.
--
-- The officer thinks in tenders. Naming the central object after our internal process
-- ("evaluation") rather than the thing they recognise is a large part of why the structure
-- read as wrong. Renaming the DB as well as the UI, not just the UI: two names for one thing
-- is exactly the drift docs/evaluate/known-pitfalls.md already records, and there are two
-- seeded rows to carry — cheap now, expensive once real data exists.
--
-- An evaluation is now something you DO to a tender, not the object itself.

begin;

alter table evaluations rename to tenders;

alter table criteria            rename column evaluation_id to tender_id;
alter table bids                rename column evaluation_id to tender_id;
alter table coi_declarations    rename column evaluation_id to tender_id;
alter table scores              rename column evaluation_id to tender_id;
alter table consensus_marks     rename column evaluation_id to tender_id;
alter table tie_break_decisions rename column evaluation_id to tender_id;
alter table audit_events        rename column evaluation_id to tender_id;

-- The sealed-bid policy names the table in its body, so it has to be rebuilt rather than
-- renamed. This is THE gate — recreate it verbatim apart from the table name.
drop policy if exists financial_sealed on bid_financials;
create policy financial_sealed on bid_financials for select using (
  authority_id = current_authority_id()
  and exists (
    select 1 from bids b join tenders t on t.id = b.tender_id
    where b.id = bid_financials.bid_id and t.technical_locked_at is not null
  )
);

-- Policies whose names embed the old word, for readability only.
alter policy eval_scope on tenders rename to tender_scope;

commit;
