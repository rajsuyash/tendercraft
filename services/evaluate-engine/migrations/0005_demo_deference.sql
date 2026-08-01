-- Demo seed correction: make the AI-deference metric tell the truth about the demo data.
--
-- F7-AC5's deference metric counts how often an evaluator's own mark, recorded BEFORE the AI
-- proposal was revealed, equalled that proposal. `docs/evaluate/DEMO.md` tells the audience:
-- "a rate near 1.00 would mean the model is really deciding — that is the metric an auditor
-- should ask for." The seeded data then showed the TEC Chair at 15/15 = 1.00 on the concluded
-- tender and 14/15 = 0.93 on the other. The demo was inviting the question and answering it
-- with the alarm value.
--
-- That was a defect in the FIXTURE, not in the metric: a seed where two evaluators
-- independently wrote exactly what the model proposed, thirty times out of thirty, does not
-- describe a committee that anyone should believe in.
--
-- **What moves and what does not.** This adjusts `ai_proposed_mark` only. `pre_reveal_mark`
-- and `final_mark` are untouched, so:
--   * every total, qualification verdict, consensus and QCBS rank is bit-identical afterwards
--     (they are computed from final_mark and consensus_marks, never from the proposal), and
--   * no row is made to say the model CHANGED anyone's mind — `amended_after_reveal` stays
--     false. The story the data now tells is the one the product exists to support: the model
--     proposed a different mark and the human's judgement stood.
--
-- Idempotent by construction. The subset is chosen from a hash of the row's own id, so running
-- this twice selects exactly the same rows and produces exactly the same end state. Selecting
-- "rows that currently match" would instead eat a further half of the remainder on every run.

update scores s
   set ai_proposed_mark = greatest(
         0,
         least(
           c.max_marks,
           -- Down by 2 normally; up by 2 when down would land back on the human's mark
           -- (a clamp at 0 would silently recreate the match this migration exists to remove).
           case when s.pre_reveal_mark - 2 = s.pre_reveal_mark or s.pre_reveal_mark - 2 < 0
                then s.pre_reveal_mark + 2
                else s.pre_reveal_mark - 2
           end
         )
       )
  from criteria c, authority_members m
 where c.id = s.criterion_id
   and m.user_id = s.evaluator_id
   and m.role = 'chair'
   -- Deterministic half, keyed on the row itself rather than on its current value.
   and (('x' || substr(md5(s.id::text), 1, 8))::bit(32)::int) % 2 = 0;

-- A model that never disagrees is not a second opinion, and a demo that shows one is arguing
-- against its own product. Anything at 0.9+ here should be read as a fixture bug, not a result.
do $$
declare worst numeric;
begin
  select max(matched::numeric / nullif(with_ai, 0)) into worst
    from (
      select count(*) filter (where s.pre_reveal_mark = s.ai_proposed_mark) as matched,
             count(*) filter (where s.ai_proposed_mark is not null)         as with_ai
        from scores s group by s.evaluator_id, s.tender_id
    ) t;
  raise notice 'highest AI-deference rate after correction: %', coalesce(worst, 0);
  if worst >= 0.9 then
    raise exception 'deference still >= 0.9 (%) — the demo would show the alarm value', worst;
  end if;
end $$;
