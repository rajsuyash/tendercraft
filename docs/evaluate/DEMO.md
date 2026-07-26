# TenderCraft Evaluate — demo guide

**Live:** https://tendercraft-evaluate-web-822379741897.europe-north1.run.app

## Sign in

| Role | Email | Password |
|---|---|---|
| Procurement Officer | `officer@pmc.test` | `Evaluate-Demo-2026!` |
| TEC Chair | `chair@pmc.test` | `Evaluate-Demo-2026!` |
| TEC Member | `rao@pmc.test` | `Evaluate-Demo-2026!` |
| Empty workspace (first-run) | `officer@greenfield.test` | `Evaluate-Demo-2026!` |

Sign in as the **Procurement Officer** for the main walkthrough.

## What is loaded

Two evaluations, deliberately at different stages so both halves of the story are visible
immediately.

**1. e-Governance Platform — parked just before the technical lock.** This is where the
product's argument lives.

**2. City Surveillance & Command Centre — concluded.** Ranked, priced, reported.

## The five-minute walkthrough

**1 · Screening matrix** (`Evaluation 1 → Screening matrix`)
Five bids against every criterion published in the RFP, each cited to its page and clause.
The three things to point at:
- *Anantha Softech* — **Fails** on turnover (₹9.4 Cr against a ₹15 Cr floor). Computed
  arithmetically; no model decided it.
- *Kaveri Technologies* — an expired ISO certificate (**Fails**) but also two criteria marked
  **Not stated**. That distinction is the point: the extractor could not find them, and a
  missing extraction must never disqualify a bidder automatically. It routes to the officer.
- Every decision carries a written reason, recorded against the officer who made it.

**2 · Technical evaluation**
Two members scored independently. On *Nexus Systems*, criterion 2, they disagree 18 vs 27.
The mean does **not** stand — the criterion shows **"Consensus required"** and the bidder's
total reads **"Not settled"**. The committee must agree a mark and record why.
Two blockers are shown: quorum (2 of 3) and the outstanding consensus.

**3 · Financial — the sealed-bid gate**
Open it. The prices are sealed, and the screen names exactly what is outstanding.
This is worth stating plainly to the officer: the prices are **not merely hidden**. They are
unreachable — enforced by the database policy, the API, and a test. There is no URL, export
or error path that returns a figure before technical scores are locked.

**4 · Evaluation 2 — the other end**
Ranked on QCBS 70:30. *Nexus* wins on both technical merit and price. Every figure traces
back: technical marks → normalised → weighted → combined.

**5 · Audit trail** (Evaluation 2)
Every action with actor and timestamp, append-only — the database refuses an update or delete
even to an administrator. Note the **AI deference** panel: how often each evaluator's own
mark, recorded *before* the AI proposal was revealed, matched that proposal. A rate near 1.00
would mean the model is really deciding. That is the metric an auditor should ask for.

**6 · Evaluation report** (Evaluation 2)
The defensible document. Every mark attributed to a named evaluator with their rationale,
COI declarations included — the chair's declared interest appears in the report, as it must.

## Questions a procurement officer will ask

**"Does the AI decide anything?"**
No. It extracts, locates evidence, and proposes a second-opinion mark *after* the evaluator
has recorded their own. Responsiveness, qualification, ranking and the gates are arithmetic
in code with 100% branch-test coverage. Every mark in the record belongs to a named person.

**"You also sell a tool that helps bidders win. How is that not a conflict?"**
Different database, different authentication, different model credential, no shared
data-access code, and a CI check (`tools/check-wall.sh`) that fails the build if anything
crosses. It is architecture, not a policy statement.

**"Where is our data?"**
Currently EU (Stockholm) — this is a **demo**. India-region hosting is a prerequisite before
any real bid data: database, compute and the model endpoint all in India. See
`docs/latency-plan.md` and PRD §8.3.

**"Can we delete our data?"**
Evaluations archive; the audit trail is append-only by design and cannot be erased in-product.
Erasure is a documented process with a named approver. That is deliberate — an audit trail
that can be quietly deleted is not an audit trail.

## Resetting the demo

```
psql "$CONN" -f services/evaluate-engine/migrations/0002_seed.sql
```
Then re-run the member/score seed. Evaluation 2's lock is applied through the API.
