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

from .types import EXTRACTION_CONFIRM_THRESHOLD, RequirementLevel

# Evidence states that mean "no usable drafted response yet".
_UNDRAFTED = {"missing", "placeholder", None}


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


_PRIORITY_ORDER = {"confirm": 0, "p0": 1, "p1": 2, "p2": 3, "covered": 4}


def _classify(
    level: RequirementLevel, verdict: str | None, draft_status: str | None, exempted: bool
) -> tuple[str, str, str]:
    """Return (priority, status, action) for one already-confirmed criterion."""
    undrafted = draft_status in _UNDRAFTED
    is_mandatory = level is RequirementLevel.MANDATORY

    if is_mandatory:
        if verdict == "fail" and not exempted:
            return "p0", "Eligibility gap — you don't currently meet this", "fix"
        if undrafted:
            return "p0", "Needs a supporting document", "upload"
        if verdict == "needs_review":
            return "p1", "Borderline — needs your review", "review"
        if draft_status == "unverified":
            return "p1", "Draft has an unverified claim to source or attest", "review"
        return "covered", "Covered by your knowledge base", "none"

    # desirable / self-attestation — never blocks the bid
    if verdict == "pass" and draft_status == "drafted":
        return "covered", "Covered by your knowledge base", "none"
    return "p2", "Good to have — improves your technical score", "optional"


def compute_readiness(
    criteria: Sequence[dict],
    analysis: dict | None,
    responses: Sequence[dict],
) -> dict:
    """Combine criteria + analysis + drafted responses into a prioritized readiness list."""
    verdict_by = {v["criterion_id"]: v for v in (analysis or {}).get("verdicts", [])}
    status_by = {r["criterion_id"]: r.get("draft_status") for r in responses}

    items: list[ReadinessItem] = []
    for c in criteria:
        cid = c["id"]
        level = RequirementLevel(c["requirement_level"])
        v = verdict_by.get(cid)
        anchor = (v or {}).get("source_anchor") or _anchor(c)

        # Fold-in of the verify step: an unconfirmed sub-0.80 extraction comes first.
        low_conf = float(c.get("confidence", 1.0)) < EXTRACTION_CONFIRM_THRESHOLD
        if low_conf and not c.get("confirmed"):
            items.append(ReadinessItem(
                cid, c["verbatim_text"], level.value, anchor, "confirm",
                "Confirm this AI-extracted requirement before matching", "confirm",
                (v or {}).get("rationale", ""), "",
            ))
            continue

        priority, status, action = _classify(
            level,
            (v or {}).get("verdict"),
            status_by.get(cid),
            bool((v or {}).get("exemption_granted", False)),
        )
        items.append(ReadinessItem(
            cid, c["verbatim_text"], level.value, anchor, priority, status, action,
            (v or {}).get("rationale", ""), (v or {}).get("gap_note", ""),
        ))

    items.sort(key=lambda i: _PRIORITY_ORDER[i.priority])

    def n(p: str) -> int:
        return sum(1 for i in items if i.priority == p)

    return {
        "summary": {
            "confirm_open": n("confirm"),
            "p0_open": n("p0"),
            "p1_open": n("p1"),
            "p2_open": n("p2"),
            "covered": n("covered"),
            "total": len(items),
            "ready_to_generate": n("confirm") == 0 and n("p0") == 0,
        },
        "items": [i.__dict__ for i in items],
    }


def _anchor(c: dict) -> str:
    if c.get("anchor_page") and c.get("anchor_clause"):
        return f"p.{c['anchor_page']} · Cl. {c['anchor_clause']}"
    return f"p.{c['anchor_page']}" if c.get("anchor_page") else "no anchor"
