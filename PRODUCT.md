# TenderCraft

**What it is.** Software for companies bidding on Indian government tenders. It reads the
tender document, tells the bidder whether they actually qualify before they spend a rupee, and
drafts the response with every claim traced back to a document the bidder already owns.

**Register.** Two surfaces, two registers.

| Surface | Register | Why |
|---|---|---|
| `/` (marketing route group) | **brand** | design IS the product; it is the front door |
| every route under `(app)` | **product** | design SERVES the work; S1–S18 in `docs/DESIGN_SPEC.md` |

**Who it is for.** Bid managers and SME owners in India, running 2–30 concurrent pursuits on
GeM, CPPP and 20+ state portals. They read 300-page PDFs for a living. A missed annexure
disqualifies a bid before anyone reads its merits, and a false claim in a submitted document
risks debarment. They are not looking for delight. They are looking for something that will
not embarrass them in front of a government buyer.

**Voice, in three physical words.** Precise. Load-bearing. Unhurried. The object it should feel
like is a well-kept engineering logbook: ruled, dated, initialled in the margin, nothing in it
that someone would not sign their name to.

**The one thing the front door must communicate.** Not speed. Every competitor sells speed.
This product's actual position is that nothing leaves it unsourced: generated sentences carry
a citation or an explicit flag, financial figures are transcluded from structured records
rather than written by a model, and a deterministic gate refuses the export when either is
untrue. Speed is the consequence, traceability is the claim.

**Non-negotiable in copy.** No claim on the marketing surface may outrun the product. ISO 27001
is on the roadmap, not held. There is no customer base yet. Percentages in
`tendercraft-PRD.md` §7 are targets, not measurements. See the CLAIMS block in
`apps/web/components/marketing/content.ts`.

**Design contract.** `design/tokens.json` and `docs/DESIGN_SPEC.md` govern the product screens
and must not be touched by marketing work. The landing page runs its own language scoped under
`.marketing`; §G of the spec lists marketing pages as a design non-goal precisely so this
separation is legitimate rather than a violation.
