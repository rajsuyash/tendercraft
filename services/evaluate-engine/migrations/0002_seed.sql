-- Demo seed. Idempotent: truncates the evaluation data it owns, then rebuilds.
--
-- Two authorities on purpose (PRD §10). Tenant A is EMPTY and stays that way — journey ACs
-- run there, and a J-AC executed against seeded data proves nothing about first-run. Tenant B
-- carries the demo content.
--
-- The seeded evaluation is deliberately parked at the most interesting moment in the journey:
-- members have scored, one criterion is in dispute, and the financial envelopes are still
-- sealed. That is the screen where the product's argument is visible in one glance.

begin;

truncate audit_events, tie_break_decisions, consensus_marks, scores, coi_declarations,
         bid_financials, bid_responses, bids, criteria, evaluations cascade;
delete from authority_members;
delete from authorities;

insert into authorities (id, name) values
  ('a0000000-0000-4000-8000-000000000001', 'Greenfield Nagar Palika — IT'),
  ('a0000000-0000-4000-8000-000000000002', 'Pune Municipal Corporation — IT');

-- Evaluation: parked just before the technical lock.
insert into evaluations (id, authority_id, title, tender_number, technical_weight,
                         financial_weight, qualifying_marks, quorum, tie_break_rule,
                         framework_locked_at, framework_locked_by)
values ('e0000000-0000-4000-8000-000000000001',
        'a0000000-0000-4000-8000-000000000002',
        'Supply, Implementation and O&M of an Integrated e-Governance Platform',
        'PMC/IT/2026/0417', 70, 30, 65, 3,
        'Higher technical score shall prevail (RFP p.41, Cl. 7.3)',
        now() - interval '6 days', null);

-- ── published criteria ─────────────────────────────────────────────────────────
-- PQ: the deterministic ones carry a comparison so screening is arithmetic, not opinion.
insert into criteria (id, authority_id, evaluation_id, kind, text, max_marks, compare_kind,
                      compare_op, compare_value, anchor_page, anchor_clause, confirmed, order_index)
values
 ('c1000000-0000-4000-8000-000000000001','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','pq',
  'Average annual turnover of the bidder for the last three financial years shall not be less than ₹15 Cr.',
  0,'numeric','>=','15',12,'3.1(a)',true,1),
 ('c1000000-0000-4000-8000-000000000002','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','pq',
  'The bidder shall hold a valid ISO 27001:2022 certificate, valid as on the bid submission date.',
  0,'date','>=','2026-07-20',13,'3.1(d)',true,2),
 ('c1000000-0000-4000-8000-000000000003','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','pq',
  'The bidder shall have completed at least two e-Governance projects of value not less than ₹4 Cr each in the last five years.',
  0,'numeric','>=','2',13,'3.1(f)',true,3),
 ('c1000000-0000-4000-8000-000000000004','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','pq',
  'The bidder shall not be blacklisted by any Central/State Government department as on the date of submission.',
  0,'boolean','=','yes',14,'3.1(h)',true,4),
 ('c1000000-0000-4000-8000-000000000005','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','pq',
  'The bidder shall furnish an Earnest Money Deposit of ₹10,00,000 in the prescribed form.',
  0,'boolean','=','yes',9,'2.7',true,5);

-- Technical: 100 marks across five criteria, mirroring how an RFP publishes them.
insert into criteria (id, authority_id, evaluation_id, kind, text, max_marks, compare_kind,
                      anchor_page, anchor_clause, confirmed, order_index)
values
 ('c2000000-0000-4000-8000-000000000001','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','technical',
  'Understanding of scope and appreciation of the Corporation''s requirements',10,'qualitative',38,'6.2(i)',true,10),
 ('c2000000-0000-4000-8000-000000000002','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','technical',
  'Proposed solution, technical architecture, security and interoperability',30,'qualitative',38,'6.2(ii)',true,11),
 ('c2000000-0000-4000-8000-000000000003','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','technical',
  'Implementation methodology, work plan and governance',25,'qualitative',39,'6.2(iii)',true,12),
 ('c2000000-0000-4000-8000-000000000004','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','technical',
  'Team composition, key personnel and deployment',20,'qualitative',39,'6.2(iv)',true,13),
 ('c2000000-0000-4000-8000-000000000005','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','technical',
  'Support, SLA and operations & maintenance approach',15,'qualitative',40,'6.2(v)',true,14);

-- ── bids ───────────────────────────────────────────────────────────────────────
insert into bids (id, authority_id, evaluation_id, bidder_name, responsive, responsive_reason)
values
 ('b0000000-0000-4000-8000-000000000001','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','Meridian Infotech Pvt Ltd', true,  'Meets all pre-qualification criteria.'),
 ('b0000000-0000-4000-8000-000000000002','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','Nexus Systems India Ltd',  true,  'Meets all pre-qualification criteria.'),
 ('b0000000-0000-4000-8000-000000000003','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','Sterling Digital Solutions', true, 'Meets all pre-qualification criteria.'),
 -- fails a mandatory PQ: turnover below the published floor
 ('b0000000-0000-4000-8000-000000000004','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','Anantha Softech Pvt Ltd',  false, 'Average annual turnover ₹9.4 Cr is below the ₹15 Cr floor at Cl. 3.1(a).'),
 -- awaiting the officer's decision: an expired certificate and an unstated project count
 ('b0000000-0000-4000-8000-000000000005','a0000000-0000-4000-8000-000000000002','e0000000-0000-4000-8000-000000000001','Kaveri Technologies Ltd',  null,  null);

-- PQ responses, with page anchors into each submission
insert into bid_responses (authority_id, bid_id, criterion_id, stated_value, excerpt, anchor_page) values
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000001','c1000000-0000-4000-8000-000000000001','24.60','Average annual turnover FY23–FY25: ₹24.60 Cr (CA certificate enclosed).',18),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000001','c1000000-0000-4000-8000-000000000002','2027-03-14','ISO/IEC 27001:2022, certificate no. IN-27001-8841, valid to 14/03/2027.',22),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000001','c1000000-0000-4000-8000-000000000003','4','Four qualifying e-Governance engagements above ₹4 Cr listed at Annexure C.',26),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000001','c1000000-0000-4000-8000-000000000004','yes','Self-declaration of non-blacklisting on ₹100 stamp paper enclosed.',31),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000001','c1000000-0000-4000-8000-000000000005','yes','EMD ₹10,00,000 by BG no. 0091/2026 of Bank of Maharashtra.',8),

 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000002','c1000000-0000-4000-8000-000000000001','31.20','Average annual turnover FY23–FY25: ₹31.20 Cr.',15),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000002','c1000000-0000-4000-8000-000000000002','2028-01-09','ISO/IEC 27001:2022 valid to 09/01/2028.',19),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000002','c1000000-0000-4000-8000-000000000003','6','Six qualifying engagements listed.',24),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000002','c1000000-0000-4000-8000-000000000004','yes','Non-blacklisting declaration enclosed.',29),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000002','c1000000-0000-4000-8000-000000000005','yes','EMD ₹10,00,000 by DD no. 774120.',7),

 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000003','c1000000-0000-4000-8000-000000000001','17.85','Average annual turnover FY23–FY25: ₹17.85 Cr.',14),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000003','c1000000-0000-4000-8000-000000000002','2026-11-30','ISO/IEC 27001:2022 valid to 30/11/2026.',20),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000003','c1000000-0000-4000-8000-000000000003','2','Two qualifying engagements listed.',23),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000003','c1000000-0000-4000-8000-000000000004','yes','Non-blacklisting declaration enclosed.',28),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000003','c1000000-0000-4000-8000-000000000005','yes','EMD ₹10,00,000 by BG no. 5512/2026.',6),

 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000004','c1000000-0000-4000-8000-000000000001','9.40','Average annual turnover FY23–FY25: ₹9.40 Cr.',11),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000004','c1000000-0000-4000-8000-000000000002','2027-05-02','ISO/IEC 27001:2022 valid to 02/05/2027.',16),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000004','c1000000-0000-4000-8000-000000000003','3','Three qualifying engagements listed.',19),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000004','c1000000-0000-4000-8000-000000000004','yes','Non-blacklisting declaration enclosed.',24),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000004','c1000000-0000-4000-8000-000000000005','yes','EMD ₹10,00,000 by DD no. 118843.',5),

 -- Kaveri: an EXPIRED certificate (definite fail) and an UNSTATED project count.
 -- "Not stated" must never auto-disqualify — it routes to a human. That distinction is the
 -- single most consequential behaviour on the screening screen.
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000005','c1000000-0000-4000-8000-000000000001','19.10','Average annual turnover FY23–FY25: ₹19.10 Cr.',13),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000005','c1000000-0000-4000-8000-000000000002','2026-05-31','ISO/IEC 27001:2013 valid to 31/05/2026.',17),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000005','c1000000-0000-4000-8000-000000000005','yes','EMD ₹10,00,000 by BG no. 3390/2026.',6);
 -- (no rows for c1…0003 / c1…0004 on purpose → "Not stated")

-- Technical evidence, so the scoring screen has something real to read
insert into bid_responses (authority_id, bid_id, criterion_id, stated_value, excerpt, anchor_page)
select 'a0000000-0000-4000-8000-000000000002', b.id, c.id, null,
  case c.order_index
    when 10 then 'Section 3 restates the Corporation''s ward-level service delivery objectives and maps each of the 14 citizen services in the RFP to a delivery milestone.'
    when 11 then 'Proposed a microservices architecture on a MeitY-empanelled cloud, API gateway with mTLS, Aadhaar-based e-KYC via an authorised ASA/KUA, and an ISO 27001-aligned SOC. Interoperability through NIC-published REST contracts.'
    when 12 then 'Five-phase implementation over 14 months with a 6-week discovery, fortnightly steering committee, and a documented rollback plan per release.'
    when 13 then 'Project Manager (PMP, 14 yrs), Solution Architect (11 yrs), 4 senior engineers, 1 security lead. CVs at Annexure F.'
    else 'Helpdesk 24x7 with L1/L2/L3 escalation, 99.5% uptime commitment, quarterly DR drills, 3-year O&M with defined penalties.'
  end, 40 + c.order_index
from bids b cross join criteria c
where b.evaluation_id = 'e0000000-0000-4000-8000-000000000001'
  and c.evaluation_id = 'e0000000-0000-4000-8000-000000000001'
  and c.kind = 'technical' and b.responsive is true;

-- ── sealed financials ──────────────────────────────────────────────────────────
-- Present in the database from ingest, unreadable through any API until technical lock.
insert into bid_financials (authority_id, bid_id, amount_inr) values
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000001', 48750000),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000002', 52400000),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000003', 44900000),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000004', 39800000),
 ('a0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000005', 46100000);

commit;
