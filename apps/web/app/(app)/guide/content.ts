/**
 * User-guide copy, kept out of the page so the markup stays readable.
 *
 * Everything here describes what the product ACTUALLY does — the stage names mirror
 * `app/deterministic/submission.py::STAGES`, the priority buckets mirror
 * `app/deterministic/readiness.py`, the section list mirrors `app/sections.py::SECTION_SPECS`,
 * the rubric mirrors `app/deterministic/rubric.py`, and the roles mirror `app/authz.py::ROLE_GRANTS`.
 * If one of those changes, this drifts — see known-pitfalls on UI arrays mirroring server enums.
 */

/**
 * The five meter stages, verbatim from `app/deterministic/submission.py::STAGES`. The journey
 * below has SIX steps, because feeding the Knowledge Base is a real thing a bidder does but is
 * not a stage the meter tracks — it feeds the ones either side of it. Rendering JOURNEY as the
 * progress strip would print "Requirements confirmed" twice and claim six stages where the
 * product counts five.
 */
export const METER_STAGES: string[] = [
  "Requirements confirmed",
  "Eligibility resolved",
  "Proposal drafted",
  "Sections approved",
  "Approvals complete",
];

export interface Stage {
  id: string;
  /** Which meter stage this step advances. Not unique — see METER_STAGES. */
  meterStage: string;
  /** Overrides the card badge where naming the meter stage would mislead. */
  badge?: string;
  title: string;
  summary: string;
  youDo: string[];
  systemDoes: string[];
  gate?: string;
  where: string;
}

export const JOURNEY: Stage[] = [
  {
    id: "upload",
    meterStage: "Requirements confirmed",
    title: "The RFP arrives — upload it",
    summary:
      "Drop the tender PDF exactly as the portal gave it to you. Nothing needs to be prepared, split, or renamed first.",
    youDo: [
      "Drop the tender package (PDF) on the upload page",
      "If pages come back unreadable, re-upload a clearer scan of just those pages",
      "Confirm any requirement the extractor was unsure about",
    ],
    systemDoes: [
      "Reads text from every page, flagging pages too poor to extract rather than guessing",
      "Reads the tender's own number, title and issuing authority off the document — not the filename",
      "Pulls out every eligibility requirement with the exact clause text and its page reference",
      "Queues anything it is less than 80% confident about for you to confirm",
    ],
    gate:
      "Requirements you have not confirmed hold the bid here. The system will not analyse eligibility against text it is not sure it read correctly.",
    where: "Tenders → Upload tender",
  },
  {
    id: "eligibility",
    meterStage: "Eligibility resolved",
    title: "Find out whether you can bid at all",
    summary:
      "Before writing a word, the tender's requirements are checked against your vendor profile. This is the 'should we bid?' answer, with the gaps quantified.",
    youDo: [
      "Keep your vendor profile current — turnover, net worth, experience records, certifications",
      "Work the checklist: upload the missing document, or fix the gap",
      "For anything you cannot meet: waive it with a reason, or mark the bid as not proceeding",
    ],
    systemDoes: [
      "Compares each requirement to your profile — numbers, dates and yes/no facts are decided arithmetically, never by a model",
      "Quantifies the shortfall rather than just failing you (“₹8.2 Cr against ₹10 Cr required — gap ₹1.8 Cr”)",
      "Applies MSE/Udyam and startup exemptions where the tender itself grants them",
      "Sorts everything into Blocks bid / Needs work / Optional so you know what actually matters",
    ],
    gate:
      "An unresolved 'Blocks bid' item stops drafting. You can override it, but the override needs a written reason and is recorded against your name.",
    where: "Tender → Bid readiness",
  },
  {
    id: "evidence",
    meterStage: "Requirements confirmed",
    badge: "Feeds every stage",
    title: "Feed it your evidence",
    summary:
      "The Knowledge Base is the corpus the drafter is allowed to quote from. Anything not in it cannot be cited, and anything that cannot be cited will not be asserted.",
    youDo: [
      "Upload past proposals, capability statements, certificates, completion certificates (PDF, DOCX, PPTX, TXT)",
      "Or point it at a public URL — your company's about page, for instance",
      "Attach a specific document to a specific requirement when you want it used there",
    ],
    systemDoes: [
      "Classifies each document and pulls out its structured facts (turnover figures, validity dates, certificate numbers)",
      "Tracks expiry — an expired certificate is hard-excluded from drafting rather than quietly used",
      "Flags unfilled template markers, so a document still saying “[Insert Designation]” cannot propagate into your bid looking sourced",
      "Splits long documents into passages so a 20-page proposal is searchable beyond its cover page",
    ],
    where: "Knowledge Base · or inline on any readiness item",
  },
  {
    id: "draft",
    meterStage: "Proposal drafted",
    title: "Generate the proposal",
    summary:
      "One action produces the full technical bid — typically 80–155 pages across 17 sections, ordered the way a bid is actually submitted.",
    youDo: [
      "Press generate once eligibility is clear",
      "Read the draft — it is a starting point authored on your behalf, not a finished document",
    ],
    systemDoes: [
      "Drafts the narrative sections against the tender's own scope and requirements",
      "Assembles the compliance forms deterministically from your profile — no model involvement",
      "Attaches a citation to every sourced sentence, and flags anything it could not source instead of inventing it",
      "Leaves an explicit placeholder where you genuinely have no evidence, rather than writing around the hole",
    ],
    where: "Tender → Bid readiness → Generate · then Proposal",
  },
  {
    id: "review",
    meterStage: "Sections approved",
    title: "Review, edit and approve each section",
    summary:
      "Nothing AI wrote leaves the building unread. Every narrative section carries an AI Draft mark until a human signs it off.",
    youDo: [
      "Read each section; edit inline wherever you want different words",
      "Resolve flagged sentences — attach a source, attest to it, or delete it",
      "Fill or remove placeholders",
      "Approve each section",
    ],
    systemDoes: [
      "Marks unapproved narrative with an AI Draft badge; your edits switch it to 'Your edit'",
      "Clears the approval when you edit — rewritten text is yours and needs signing again",
      "Counts every unapproved narrative section as an open blocker on the readiness meter",
      "Scores the draft on the nine evaluation dimensions and tells you which sections cost you the most marks",
    ],
    gate:
      "Any narrative section with AI-authored sentences and no human approval is a blocker. This is the control that replaces cite-or-flag for prose that has nothing to cite.",
    where: "Proposal · Technical score",
  },
  {
    id: "signoff",
    meterStage: "Approvals complete",
    title: "Sign off and export",
    summary:
      "The final gate is deterministic: the compliance matrix is computed, every blocker is named, and the export button stays disabled until it is clean.",
    youDo: [
      "Route the proposal through the four approval stages: review, compliance, legal, final",
      "Clear any remaining blockers the matrix names",
      "Export the DOCX",
    ],
    systemDoes: [
      "Builds the compliance matrix — requirement by requirement, with the response section and evidence against each",
      "Refuses export outright on an uncited financial or numeric claim; this one cannot be overridden by anybody",
      "Checks that more than one person signed the chain, separately from counting the signatures",
      "Logs every approval, override and export to an append-only audit trail",
    ],
    gate:
      "Admin override can clear soft blockers, and is recorded. It cannot clear an uncited financial claim — that blocker is absolute.",
    where: "Proposal → Compliance & export",
  },
];

export const PRIORITIES: { label: string; chip: string; means: string; blocks: string }[] = [
  {
    label: "CONFIRM",
    chip: "bg-primary-tint text-primary",
    means: "The extractor was unsure it read this correctly. Check it against the source clause.",
    blocks: "Yes — until confirmed",
  },
  {
    label: "Blocks bid",
    chip: "bg-danger-bg text-danger",
    means:
      "A mandatory requirement you do not currently meet, or one with no evidence behind it.",
    blocks: "Yes — resolve or waive with a reason",
  },
  {
    label: "Needs work",
    chip: "bg-warning-bg text-warning",
    means:
      "Borderline, or eligible but missing the document that proves it. Worth fixing before you submit.",
    blocks: "No",
  },
  {
    label: "Optional",
    chip: "bg-info-bg text-info",
    means: "Not mandatory. Addressing it improves your technical score.",
    blocks: "No",
  },
  {
    label: "COVERED",
    chip: "bg-success-bg text-success",
    means: "Met, with evidence attached.",
    blocks: "No",
  },
];

export const SECTION_GROUPS: {
  title: string;
  kind: "AI-drafted" | "Assembled";
  note: string;
  items: string[];
}[] = [
  {
    title: "Narrative sections",
    kind: "AI-drafted",
    note: "Written for you, then flagged AI Draft until a human approves each one.",
    items: [
      "Form 5: Letter of Proposal",
      "Form 7(b): Understanding of the Project",
      "Form 7(a): Proposed Solution and Technical Architecture",
      "Form 7(c): Technical Approach and Methodology",
      "Form 8: Proposed Work Plan",
      "Quality Assurance and Testing Approach",
      "Training and Capacity Building",
      "Support, SLA and Operations & Maintenance",
      "Risk Management and Mitigation",
    ],
  },
  {
    title: "Compliance forms",
    kind: "Assembled",
    note: "Built from your profile and the tender's requirements. No model writes these.",
    items: [
      "Form 1: Compliance Sheet for Pre-Qualification",
      "Form 9: Team Composition",
      "Form 10: Curriculum Vitae of Key Personnel",
      "Form 11: Deployment of Personnel",
      "Form 6: Project Citation Format",
      "Form 12: Deviations",
      "Technical Compliance Matrix",
      "Annexures and Evidence Index",
    ],
  },
];

export const RUBRIC_DIMENSIONS: { label: string; weight: number }[] = [
  { label: "Proposed solution & technology", weight: 20 },
  { label: "Approach, methodology & work plan", weight: 15 },
  { label: "Team composition & key personnel", weight: 15 },
  { label: "Relevant experience & past performance", weight: 15 },
  { label: "Understanding of scope", weight: 10 },
  { label: "Quality assurance & testing", weight: 8 },
  { label: "Support, SLA & O&M", weight: 7 },
  { label: "Training & capacity building", weight: 6 },
  { label: "Risk management & mitigation", weight: 4 },
];

export const FEATURES: { name: string; href?: string; what: string; detail?: string }[] = [
  {
    name: "Dashboard",
    href: "/dashboard",
    what: "Every live bid, sorted by how soon it is due.",
    detail:
      "Deadline chips escalate as the date closes in. Click any bid to land on its readiness hub.",
  },
  {
    name: "Tenders",
    href: "/tenders",
    what: "Your whole pursuit portfolio, searchable and filterable by project.",
  },
  {
    name: "Bid readiness",
    what: "The hub for a single tender — one meter, one checklist, one place to act.",
    detail:
      "Replaces four counters that used to disagree with each other. The percentage and the list of what is left are computed together, so they cannot drift apart.",
  },
  {
    name: "Vendor profile",
    href: "/profile",
    what: "The structured facts every eligibility check runs against.",
    detail:
      "Legal identity, year-by-year turnover, net worth, experience records and certifications with their validity. The completeness meter names how many items are blocking accurate analysis. Editable in place.",
  },
  {
    name: "Knowledge Base",
    href: "/library",
    what: "Your evidence corpus — the only thing the drafter may quote.",
    detail:
      "Upload files or ingest a URL. Documents are classified, their key figures extracted, and their expiry tracked. Expired documents are excluded from drafting, not silently used.",
  },
  {
    name: "Past bids",
    href: "/library",
    what: "Proposals you have already submitted, mined into answers you can reuse.",
    detail:
      "Changes how a draft SOUNDS and what you can reuse — never what is claimed, cited or scored. A prior answer is suggested with the bid it came from, its authority and its outcome, and it is re-checked against today's evidence before you accept it: if the certificate that backed it has since expired, you are told which one and when. Won, lost and unknown bids all count; a bid is usually lost on price, not on its methodology section.",
  },
  {
    name: "Proposal",
    what: "The full document, section by section, with inline editing and per-section approval.",
    detail:
      "AI Draft and Your edit badges tell you the provenance of every section at a glance. Regenerate re-drafts from current evidence.",
  },
  {
    name: "Technical score",
    what: "How an evaluation committee would likely mark the proposal you have right now.",
    detail:
      "Reads the actual document rather than predicting from your profile, so improving a section moves the number. Each suggestion is labelled with the marks it should add.",
  },
  {
    name: "Compliance & export",
    what: "The final gate, plus the DOCX.",
    detail:
      "The compliance matrix pairs every requirement with your response and its evidence. The export button is disabled — not just the endpoint — while any blocker is open.",
  },
  {
    name: "Settings",
    href: "/settings",
    what: "Team, roles, approval chain and the audit log.",
    detail:
      "Invite members, assign roles, and read the immutable record of every override, approval and export.",
  },
  {
    name: "Workspaces",
    what: "One workspace per client engagement, fully walled off from the others.",
    detail:
      "Switch from the top of the sidebar. Data never crosses between workspaces — each query is scoped to the one you are in.",
  },
];

export const ROLES: { role: string; can: string }[] = [
  { role: "Writer", can: "Read, draft and upload evidence." },
  { role: "Reviewer", can: "Everything a writer can, plus sign the review stage." },
  { role: "Compliance checker", can: "Read, and sign the compliance stage." },
  { role: "Legal", can: "Read, and sign the legal stage." },
  { role: "Approver", can: "Read, and sign the final stage." },
  {
    role: "Admin",
    can: "Everything, including the logged export override and managing members.",
  },
];

export const GUARANTEES: { title: string; detail: string }[] = [
  {
    title: "It will not invent a number",
    detail:
      "Financial and numeric values come from your structured data, not from prose a model wrote. An uncited financial claim blocks export absolutely — no override, for anyone.",
  },
  {
    title: "It will not decide your eligibility",
    detail:
      "Verdicts on numbers, dates and yes/no requirements are arithmetic. The model reads and writes; code decides.",
  },
  {
    title: "It will not claim you enclosed something",
    detail:
      "The drafter cannot see what you will attach, so it never writes “enclosed” or “attached”. A document that contradicts its own compliance matrix is a false statement to a public buyer.",
  },
  {
    title: "It will not treat the tender as instructions",
    detail:
      "Tender documents are untrusted input. Text inside them is data to be extracted — it can never direct the system to do anything.",
  },
  {
    title: "It will not let one person sign everything",
    detail:
      "The export gate checks how many distinct people signed the approval chain, separately from how many signatures exist.",
  },
  {
    title: "It will not quietly lose the record",
    detail:
      "The audit trail is append-only. Overrides, approvals, watermark removals and exports cannot be edited or deleted afterwards — not even by an administrator.",
  },
];
