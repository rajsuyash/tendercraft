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

## Creating a tender from scratch (new)

The officer can now run the whole journey without anyone touching the database:

**Tenders → Open a tender** → enter the title, number, weights and quorum → **upload the RFP
PDF**. The criteria, marks and thresholds are read out of it, each anchored to the page and
clause it came from. Confirm each one (the lock stays disabled until you do — an extracted
criterion that no person has vouched for cannot govern a public tender), then **Lock framework**.

**Bids tab** → enter a bidder name and quoted price → upload their proposal PDF. Their answer to
each published criterion is located and cited to a page. The screening matrix computes
responsiveness arithmetically from those values.

## The throughput features (new — milestones N1–N5)

These answer the officer pain points TP6, TP11, TP17 and TP40. Demo them in this order; each
one is a screen you can point at.

**0. Write the tender in the first place (TP1 — Drafts, in the sidebar).** This is the step
*before* everything else, and it is the one procurement officers rank as their worst pain: RFPs
get written in Word from a reused template, emailed round, and reviewed by the legal cell after
the ambiguity is already baked in.

*New draft* → title, number, category. Then enter the money and the criteria and **watch the
right-hand panel**. The checks run against GFR 2017 and the 2022 Procurement Manuals as you
type. A good live demo is to type a deliberately bad tender:

| Enter this | What fires |
|---|---|
| Turnover bar of ₹20 Cr on a ₹5 Cr tender | **R1** — at most ₹10,00,00,000 (2× the estimated value) |
| Submission window of 10 days | **R2** — at least 21 days |
| Single envelope | **R3** — two-envelope required above the threshold |
| “Core switches shall be Cisco Catalyst 9300” | **R4** — names a brand with no “or equivalent” |
| EMD of 8%, no exemption clause | **R6** — twice: outside the 1–3% band, and no MSE/startup exemption |
| A technical criterion with no marking scheme | **R9** — state how it will be evaluated |

Each finding names **what would satisfy it**, not just what is wrong. Fix them and the panel
empties. Three things to land while you are here:
- **Publish stays disabled** until every blocking finding is cleared *and* legal, finance and
  technical have signed off. Reviewers all see it at once — sequential email review is exactly
  why the legal cell reviews late.
- **Edit anything after a sign-off and the sign-off is revoked.** Approval of wording that then
  changed is not approval. Demo it: sign off all three, change a field, watch them reset.
- **Publishing creates the tender with the criteria already in it** — zero retyping. You land on
  the framework page of a real tender. That is the join between this module and everything the
  product already did, and it is why the published document and the scoring framework cannot
  drift apart.

Checks that cannot run (because a figure has not been entered yet) are listed separately and
**never** count as passes. A draft must not acquire a clean bill of health it did not earn.

**1. Drop the whole folder (TP6 — Bids tab).** Drag the entire portal download, or one ZIP, at
the dropzone. It unpacks, reads PDFs, scans and spreadsheets alike, works out which bidder sent
each file from the letterhead — not the filename, because portal downloads are all called
`bid_1.pdf` — and files each as technical or financial. Point out three things:
- the **evidence quote** next to each guess, with its page. That is what lets an officer catch
  the trap where an OEM authorisation names the manufacturer, not the bidder.
- anything it is not sure about goes to **triage**, never a guess.
- **screening refuses to open** while triage is non-empty. A matrix built on a partial set of
  files looks finished and is not, and a bidder can be excluded off it.

**2. Triage (Bids → the amber banner).** One card per unmatched file with the evidence and the
candidate bidders. Settling them drops the count to zero and screening unlocks.

**3. Mandatory documents (TP11 — Documents tab).** *Build it from the published criteria* turns
the officer's printed EMD/affidavit/certificate checklist into a matrix of bidders × documents.
Say plainly: **"Received" means a document of the right type is on file — not that it is
correct.** That judgement stays human. And note that nothing is ever marked *not received* while
any file is still unmatched: a bidder must never be failed on our unfinished reading.

**4. Technical compliance (TP17 — Compliance tab).** Every technical requirement against what
each bid actually offers, with the page it was read from. The counter is the point: `3/5
answered · 2 need you` turns "read four hundred pages" into "read these two things". Stress that
this screen is **evidence, not a verdict** — "not found" is a statement about our reading of the
document, never a finding against the bidder.

**5. Outcome letters (TP40 — Outcome tab, concluded tender only).** Award and regret letters
written from the evaluation record, no figure retyped. The line to land: each letter is
assembled from **only what that recipient may see** — their own marks and rank, plus the
winner's name and accepted price. The footer names how many internal fields the disclosure
filter withheld. Try the Outcome tab on the *unconcluded* tender to show it refuses: the letters
state an accepted price, so they cannot exist before the technical lock.

Sample PDFs for a live demo are in `.playwright-mcp/fx/` (one RFP, two bids — one qualifying,
one that fails on turnover, an expired certificate and project count).

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

## Running it locally

Production has everything it needs. For a local run the engine also wants a model credential,
which is not in `.env` by default:

```
EVAL_MODEL_API_KEY=<same value as GEMINI_API_KEY>
EVAL_WALL_ALLOW_SHARED_KEY=1
```

The second line is not optional: `tools/check-wall.sh` compares the two keys and **fails by
default**, so the shared-credential waiver (F13-AC3) stays visible in every CI run instead of
quietly becoming permanent. Retire both before the first production authority.

Without the key nothing breaks — attribution simply returns "no proposal", which is the designed
degradation, and every uploaded file waits in triage for a human.
