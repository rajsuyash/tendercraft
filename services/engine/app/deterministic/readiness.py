"""Bid-readiness priority layer (P0/P1/P2) — the bidder-facing "what do I still need" view.

Pure function over data other modules already produce: criteria (requirement level +
confidence/confirmed), the eligibility analysis (verdicts + gaps), and the drafted proposal
responses (evidence coverage). Priority is by BLOCKING IMPACT:

  confirm  — AI extraction below 0.80 and not yet human-confirmed (fold-in of the verify step)
  P0       — mandatory AND (eligibility Fail, unexempted, OR no drafted evidence) → rejection risk
  P1       — mandatory AND (borderline Needs-review OR a draft flagged unverified) → risky
  P2       — desirable / self-attestation not fully covered → improves score, won't disqualify
  covered  — mandatory Pass with a clean drafted response

No model calls, no I/O — 100%-branch testable like the other gate modules.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .requirement_kind import effective_kind
from .types import EXTRACTION_CONFIRM_THRESHOLD, RequirementKind, RequirementLevel

# Evidence states that mean "no usable drafted response yet".
_UNDRAFTED = {"missing", "placeholder", None}
# Decisions the bidder can make that soften a P0 block (accept-the-gap vs drop-the-requirement).
# Both stop a P0 from blocking generation; the difference is intent/labeling only.
OVERRIDDEN_DECISIONS = {"ignore", "do_not_proceed"}
_DEFAULT_DECISION = "resolve"


@dataclass(frozen=True)
class ReadinessItem:
    criterion_id: str
    verbatim_text: str
    requirement_level: str
    source_anchor: str
    priority: str  # "confirm" | "p0" | "p1" | "p2" | "covered"
    status: str  # human-facing one-liner
    action: str  # "confirm" | "upload" | "fix" | "review" | "optional" | "none"
    rationale: str
    gap_note: str
    decision: str  # "resolve" | "ignore" | "do_not_proceed"
    comment: str
    document_id: str | None


_PRIORITY_ORDER = {"confirm": 0, "p0": 1, "p1": 2, "p2": 3, "covered": 4}


#: What a non-gate requirement says on the checklist. None of these can pass or fail, so none
#: of them blocks: an obligation binds after award, an instruction tells you how to bid, a form
#: is a template to attach, a spec belongs to the schedule screen. Before kinds existed they
#: were all evaluated as eligibility and all read "Run analysis to check eligibility" — which
#: is how eighteen mandatory rows on a catalogue bid produced a NO-BID.
_NON_GATE_STATUS = {
    RequirementKind.OBLIGATION: (
        "Post-award duty — plan for it; it does not affect eligibility", "review",
    ),
    RequirementKind.INSTRUCTION: ("How to submit — follow it when you bid", "review"),
    RequirementKind.FORM: ("A form to fill in and attach", "upload"),
    RequirementKind.SPEC: ("A technical parameter — see schedule fit", "review"),
}


#: What a criterion the CLASSIFIER called a gate and the READING found nothing checkable in
#: says. It is not an eligibility question, so it must not block, and the wording matches the
#: analysis screen's own note rather than inventing a second vocabulary for the same row.
_UNSCORED_GATE = (
    "Reads like eligibility, but states nothing checkable against your profile", "review",
)


def _classify(
    level: RequirementLevel, verdict: str | None, draft_status: str | None, exempted: bool,
    kind: RequirementKind = RequirementKind.GATE, scored: bool = True,
) -> tuple[str, str, str]:
    """Return (priority, status, action) for one already-confirmed criterion.

    A NON-GATE never reaches the eligibility branches below. It has no verdict — `analyze`
    does not evaluate it — and the mandatory fallthrough is "no verdict yet, block until
    matched", so without this branch every post-award obligation would become a blocking P0
    the moment gates started being filtered. That would be a worse regression than the defect
    being fixed, and it is invisible from the analysis side.
    """
    if kind is not RequirementKind.GATE:
        status, action = _NON_GATE_STATUS[kind]
        return "p2", status, action
    if not scored:
        # A gate `analyze` declined to score. The classifier reads the sentence's vocabulary
        # and the extractor read the whole clause; when they disagree the extractor wins, and
        # the row moves to the analysis checklist with no verdict.
        #
        # Without this branch it falls through to the mandatory no-verdict case below and
        # becomes a blocking P0 reading "Run analysis to check eligibility" — on a criterion
        # the analysis HAS run against and will never produce a verdict for. Measured live on
        # the Oil India bid: five such rows, so `ready_to_generate` was false and the Generate
        # button was replaced by "Clear the blocking items first", pointing at five items no
        # user could ever clear. That is the same dead end the non-gate branch above exists to
        # prevent, arriving through a second door.
        return "p2", *_UNSCORED_GATE

    undrafted = draft_status in _UNDRAFTED
    is_mandatory = level is RequirementLevel.MANDATORY

    if is_mandatory:
        # Eligibility is decided deterministically (PRD §2.4). Only a real eligibility FAIL is a
        # blocking P0. A missing/placeholder DRAFT on a criterion the bidder actually MEETS is a
        # proposal-completion task (P1) — the export gate enforces "no placeholder" at export,
        # so it must not block the bid decision here.
        if verdict == "fail" and not exempted:
            return "p0", "Eligibility gap — you don't currently meet this", "fix"
        if verdict == "needs_review":
            return "p1", "Borderline — needs your review", "review"
        if verdict == "pass" or exempted:
            if draft_status == "unverified":
                return "p1", "Draft has an unverified claim to source or attest", "review"
            if undrafted:
                return "p1", "Eligible — add a document to complete the response", "upload"
            return "covered", "Covered by your knowledge base", "none"
        # No verdict yet (analysis not run) — conservative: block until matched.
        return "p0", "Run analysis to check eligibility", "upload"

    # desirable / self-attestation — never blocks the bid
    if verdict == "pass" and draft_status == "drafted":
        return "covered", "Covered by your knowledge base", "none"
    return "p2", "Good to have — improves your technical score", "optional"


def compute_readiness(
    criteria: Sequence[dict],
    analysis: dict | None,
    responses: Sequence[dict],
    decisions: Sequence[dict] = (),
) -> dict:
    """Combine criteria + analysis + drafted responses + bidder decisions into a prioritized list.

    A P0 item the bidder has chosen to ignore or drop no longer blocks generation (it's still
    shown, styled as overridden). `ready_to_generate` gates on the *blocking* P0 count only.
    """
    verdict_by = {v["criterion_id"]: v for v in (analysis or {}).get("verdicts", [])}
    # Which gates `analyze` declined to score. A checklist entry carrying a `note` is a
    # DEMOTED gate; entries without one were never gates and are covered by their kind.
    unscored = {
        c["criterion_id"] for c in (analysis or {}).get("checklist", []) if c.get("note")
    }
    status_by = {r["criterion_id"]: r.get("draft_status") for r in responses}
    decision_by = {d["criterion_id"]: d for d in decisions}

    items: list[ReadinessItem] = []
    for c in criteria:
        cid = c["id"]
        level = RequirementLevel(c["requirement_level"])
        v = verdict_by.get(cid)
        anchor = (v or {}).get("source_anchor") or _anchor(c)
        d = decision_by.get(cid) or {}
        decision = d.get("decision") or _DEFAULT_DECISION
        comment = d.get("comment") or ""
        document_id = d.get("document_id")

        # Fold-in of the verify step: an unconfirmed sub-0.80 extraction comes first.
        low_conf = float(c.get("confidence", 1.0)) < EXTRACTION_CONFIRM_THRESHOLD
        if low_conf and not c.get("confirmed"):
            items.append(ReadinessItem(
                cid, c["verbatim_text"], level.value, anchor, "confirm",
                "Confirm this AI-extracted requirement before matching", "confirm",
                (v or {}).get("rationale", ""), "", decision, comment, document_id,
            ))
            continue

        priority, status, action = _classify(
            level,
            (v or {}).get("verdict"),
            status_by.get(cid),
            bool((v or {}).get("exemption_granted", False)),
            effective_kind(c),
            cid not in unscored,
        )
        items.append(ReadinessItem(
            cid, c["verbatim_text"], level.value, anchor, priority, status, action,
            (v or {}).get("rationale", ""), (v or {}).get("gap_note", ""),
            decision, comment, document_id,
        ))

    items.sort(key=lambda i: _PRIORITY_ORDER[i.priority])

    def n(p: str) -> int:
        return sum(1 for i in items if i.priority == p)

    p0_overridden = sum(
        1 for i in items if i.priority == "p0" and i.decision in OVERRIDDEN_DECISIONS
    )
    p0_blocking = n("p0") - p0_overridden

    return {
        "summary": {
            "confirm_open": n("confirm"),
            "p0_open": n("p0"),
            "p0_blocking": p0_blocking,
            "p0_overridden": p0_overridden,
            "p1_open": n("p1"),
            "p2_open": n("p2"),
            "covered": n("covered"),
            "total": len(items),
            "ready_to_generate": n("confirm") == 0 and p0_blocking == 0,
        },
        "items": [i.__dict__ for i in items],
    }


def _anchor(c: dict) -> str:
    if c.get("anchor_page") and c.get("anchor_clause"):
        return f"p.{c['anchor_page']} · Cl. {c['anchor_clause']}"
    return f"p.{c['anchor_page']}" if c.get("anchor_page") else "no anchor"
