/**
 * Guide copy. Everything here describes what the product ACTUALLY does — stage names mirror
 * services/evaluate-engine/evaluate/deterministic/gates.py, verdicts mirror screening.py, and
 * the thresholds mirror the seeded framework. If those change, this drifts.
 */

export const STAGES: {
  n: number; title: string; who: string; summary: string;
  gate?: string;
}[] = [
  {
    n: 1, title: "Publish the framework", who: "Procurement Officer",
    summary:
      "The criteria, marks, weights and qualifying threshold are taken from the RFP as published, confirmed, then locked.",
    gate:
      "Once locked, the framework is immutable. You evaluate against what was published — a criterion cannot be invented or reweighted after bids are open.",
  },
  {
    n: 2, title: "Constitute the committee", who: "Procurement Officer",
    summary:
      "Members are added and each records a conflict-of-interest declaration. A declared interest does not exclude anyone; it is recorded and printed in the report.",
    gate: "A member with no declaration cannot reach any scoring screen.",
  },
  {
    n: 3, title: "Screen the bids", who: "Procurement Officer",
    summary:
      "Every bid is compared against every pre-qualification criterion. Numeric, date and yes/no comparisons are computed — no model decides responsiveness.",
    gate:
      "A non-responsive decision requires a written reason and is recorded against the officer who made it. A non-responsive bid cannot be scored.",
  },
  {
    n: 4, title: "Score independently", who: "TEC Members",
    summary:
      "Each member scores each responsive bid alone. Your own mark is recorded before any AI second opinion is shown.",
  },
  {
    n: 5, title: "Reconcile and lock", who: "TEC Chair",
    summary:
      "Where members diverge, the committee agrees one mark and records why. Then the technical scores are locked.",
    gate:
      "The lock is blocked below quorum, and blocked while any disputed criterion is unresolved.",
  },
  {
    n: 6, title: "Open the financial envelopes", who: "Procurement Officer",
    summary:
      "Only now, and only for technically qualified bidders. Combined QCBS ranking follows.",
    gate:
      "This is the two-bid rule. Before the technical lock there is no route to a price — not through the page, the API, an export, or an error response.",
  },
];

export const VERDICTS: { label: string; cls: string; means: string; blocks: string }[] = [
  {
    label: "Meets", cls: "bg-success-bg text-success",
    means: "The published requirement was compared arithmetically and the bid satisfies it.",
    blocks: "No",
  },
  {
    label: "Fails", cls: "bg-danger-bg text-danger",
    means: "The comparison was made and the bid does not satisfy it — e.g. turnover below the published floor.",
    blocks: "Proposes non-responsive; the officer still decides and records a reason",
  },
  {
    label: "Not stated", cls: "bg-warning-bg text-warning",
    means:
      "The value could not be found in the submission. This is NOT a failure — an extraction miss must never disqualify a bidder, so it is routed to you.",
    blocks: "Requires your decision",
  },
  {
    label: "Review", cls: "bg-info-bg text-info",
    means: "A qualitative criterion. The system locates the evidence; a human judges it.",
    blocks: "Requires your decision",
  },
];

export const GUARANTEES: { title: string; detail: string }[] = [
  {
    title: "No AI decides anything",
    detail:
      "Responsiveness, qualification, the committee mark, the ranking and every gate are arithmetic in code, tested to 100% branch coverage. The model extracts, locates evidence and offers a second opinion after you have recorded your own mark.",
  },
  {
    title: "No price before the technical lock",
    detail:
      "Financial envelopes are stored separately from the moment of upload, and the seal is enforced in the database policy, the API handler and an automated test. Reaching a figure early would invalidate the tender.",
  },
  {
    title: "No mark without a name",
    detail:
      "Every mark carries the evaluator who gave it and their written rationale. There is no system-authored score anywhere in the record.",
  },
  {
    title: "No silent averaging",
    detail:
      "Where members disagree beyond the threshold, the mean does not stand. The criterion has no committee mark at all until the chair records an agreed one and says why.",
  },
  {
    title: "No invented tie-break",
    detail:
      "Equal combined scores are reported as a tie. The rule the RFP published is shown, and a named person records what was applied. Software never picks the winner.",
  },
  {
    title: "No editable audit trail",
    detail:
      "Every action is append-only. The database refuses an update or a delete, including from an administrator.",
  },
  {
    title: "No contact with the bidder-assistance product",
    detail:
      "TenderCraft also sells a tool that helps bidders write proposals. This product runs on a different database with different credentials and no shared data-access code, and a build check fails if anything crosses.",
  },
];

export const DEFERENCE = {
  title: "Why we measure how often you agree with the AI",
  body:
    "Each score stores the mark you gave before the proposal was revealed, alongside your final mark. The audit screen shows, per evaluator, how often those matched. A rate near 1.00 across many marks is the signal that the model — not the person — is effectively deciding. It is the number an auditor should ask for, and the reason your own mark is captured first.",
};
