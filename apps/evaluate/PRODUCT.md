# TenderCraft Evaluate

**What it is.** Software for the government authority on the other side of the tender. It
absorbs the bids an authority has received — whatever formats they arrived in — checks them
against the criteria that authority published, and carries a committee through screening,
scoring and ranking to a recommendation it can defend at audit. It does not decide anything.

**Register.** Two surfaces, two registers.

| Surface | Register | Why |
|---|---|---|
| `/` (`public/landing.html`) | **brand** | design IS the product; it is the front door for an authority that has never heard of us |
| every route under `(app)` | **product** | design SERVES the work; a committee is mid-evaluation with a statutory clock running |

**Who it is for.** Procurement officers, technical evaluation committee members and chairs in
Indian central and state authorities — municipal corporations, PSUs, departments. They are
usually evaluating one high-value tender at a time under a 30-day clock, with five to fifteen
bids arriving as a folder of PDFs, scans and spreadsheets from GeM, CPPP or a state portal.
Their exposure is asymmetric and personal: a bidder they wrongly excluded can challenge the
award, a CAG audit can revisit a mark two years later, and their name is on it. They are not
looking for speed. They are looking for a conclusion that survives being questioned.

**Voice, in three physical words.** Precise. Accountable. Unhurried. The object it should feel
like is a bound minute book: every entry dated, attributed and in ink, with nothing that can be
quietly amended after the fact.

**The one thing the front door must communicate.** Not automation. Every competitor sells
"evaluate bids faster with AI", and to this buyer that sentence reads as *a machine will make a
decision I have to sign*. The actual position is the opposite and it is structural: the AI reads
and cites, and code decides. Responsiveness, qualification, ranking and the sealed-bid gate are
arithmetic with no model in the path, tested to full branch coverage. Every technical mark
belongs to a named person who recorded it before any AI proposal was revealed. Speed is a
consequence of not having to re-read; the claim is that the authority never lost control of the
decision.

**The three proofs that carry the page.**

1. **Verdicts are computed, not scored.** A turnover threshold either clears or it does not.
   Shown as a real screening row with the value found and the page it came from.
2. **Sealed bids are unreachable, not hidden.** Prices are refused by the database policy, the
   API and an integration test until technical scores are locked. "Hidden" is a UI claim;
   "unreachable" is an architectural one, and only the second one survives a challenge.
3. **The wall.** We also sell software that helps firms bid. The two products share no database,
   no credential and no data-access code, and a CI check fails the build if that changes. Say it
   before the buyer asks — they will ask.

**Non-negotiable in copy.** No claim may outrun the product. There is no customer base, no
security certification, and no India-region residency yet — the demo runs in the EU. The GFR
rulepack is implemented but awaits a procurement-legal review of its citations. Where a
competitor would put a win rate or a logo wall, this page puts what is verifiable in the
repository and states the gaps in its own words. A false claim to a government buyer is not a
marketing risk; it is a procurement disqualification.

**Words we do not use.** "Automated scoring", "AI-generated score", "semantic similarity" as a
basis for a mark, "100% compliance", "risk detection" — each describes something the product
deliberately refuses to do, and using them would discard the only differentiator that lets us
sell to an authority at all. "Not stated" is never a synonym for non-compliance: it is a
statement about our reading, not about the bidder.

**Design contract.** The landing page is the design team's Stitch export — `public/landing.html`
with its system recorded in `marketing/DESIGN.md` at the repo root. It is treated as authored
artwork: colour, spacing, type and layout are preserved byte-for-byte, and enhancement is added
as a runtime layer scoped to `data-` attributes rather than by editing their markup. Product
screens are governed separately by `docs/evaluate/` and `tendercraft-evaluate-PRD.md`; marketing
work must not touch them.
