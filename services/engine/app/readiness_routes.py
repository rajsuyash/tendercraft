"""Bid-readiness orchestration (Module A–D unified for the bidder).

`prepare` runs the whole match in one call — lock → eligibility analysis → draft-match — then
`readiness` reads the stored results and returns the prioritized P0/P1/P2 checklist.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import analysis, db
from .auth import AuthedUser, get_current_user
from .deterministic import submission
from .deterministic.lock import evaluate_lock
from .deterministic.readiness import OVERRIDDEN_DECISIONS, compute_readiness
from .deterministic.types import Criterion, RequirementLevel, SourceAnchor
from .envelope import ApiError, ok

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


class DecisionIn(BaseModel):
    decision: Literal["resolve", "ignore", "do_not_proceed"] | None = None
    comment: str | None = Field(default=None, max_length=2000)


def _to_domain(row: dict) -> Criterion:
    anchor = None
    if row.get("anchor_page") and row.get("anchor_clause"):
        anchor = SourceAnchor(page=row["anchor_page"], clause=row["anchor_clause"])
    return Criterion(
        id=row["id"], confidence=float(row["confidence"]), confirmed=bool(row["confirmed"]),
        requirement_level=RequirementLevel(row["requirement_level"]), anchor=anchor,
    )


def _readiness_payload(workspace_id: str, tender_id: str) -> dict:
    criteria = db.get_criteria(tender_id, workspace_id)
    analysis_result = db.get_analysis(tender_id, workspace_id)
    proposal = db.get_proposal_by_tender(tender_id, workspace_id)
    responses = db.get_responses(proposal["id"], workspace_id) if proposal else []
    decisions = db.get_readiness_decisions(tender_id, workspace_id)
    return compute_readiness(criteria, analysis_result, responses, decisions)


@router.get("/api/tenders/{tender_id}/readiness")
def get_readiness(tender_id: str, user: CurrentUser) -> dict:
    if not db.get_tender(tender_id, user.workspace_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    return ok(_readiness_payload(user.workspace_id, tender_id))


@router.put("/api/tenders/{tender_id}/criteria/{criterion_id}/decision")
def set_decision(tender_id: str, criterion_id: str, body: DecisionIn, user: CurrentUser) -> dict:
    """Record the bidder's per-item decision (resolve/ignore/do_not_proceed) + comment. Ignoring or
    dropping a P0 softens the deterministic block, so those decisions are audited."""
    # ET-6 + integrity: the criterion must belong to this tender AND this workspace before we write.
    if not db.get_criterion_in_tender(criterion_id, tender_id, user.workspace_id):
        raise ApiError(404, "CRITERION_NOT_FOUND", "criterion not found in this tender")
    # Audit BEFORE softening the gate: an override must never take effect without an audit trail.
    if body.decision in OVERRIDDEN_DECISIONS:
        db.write_audit(
            user.workspace_id, user.user_id, "readiness_decision", "criterion", criterion_id,
            after={"decision": body.decision},
        )
    db.upsert_readiness_decision(
        user.workspace_id, tender_id, criterion_id,
        decision=body.decision, comment=body.comment, actor=user.user_id,
    )
    return ok(_readiness_payload(user.workspace_id, tender_id))


def _prepare(workspace_id: str, tender_id: str) -> dict:
    from .proposal_routes import do_generate

    criteria = db.get_criteria(tender_id, workspace_id)
    # 1. Lock the TOM (human confirmation of low-confidence items is enforced by the gate).
    lock = evaluate_lock([_to_domain(c) for c in criteria])
    if not lock.ok:
        raise ApiError(409, "LOCK_BLOCKED", " | ".join(lock.blockers))
    db.set_tender_locked(tender_id, workspace_id, datetime.now(UTC).isoformat())

    # 2. Eligibility analysis (matches criteria against the structured profile).
    profile = db.get_profile_context(workspace_id)
    db.save_analysis(workspace_id, tender_id, analysis.analyze(criteria, profile))

    # 3. Draft-match against the content library.
    do_generate(workspace_id, tender_id)

    return _readiness_payload(workspace_id, tender_id)


@router.get("/api/tenders/{tender_id}/submission")
def submission_state(tender_id: str, user: CurrentUser) -> dict:
    """One "how close am I to submitting" figure, with every blocker named.

    Replaces four counters that described the same bid and disagreed. Computed from the same
    rows the gates use, so the number and its explanation cannot drift apart.
    """
    if not db.get_tender(tender_id, user.workspace_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")

    readiness = _readiness_payload(user.workspace_id, tender_id)["summary"]
    proposal = db.get_proposal_by_tender(tender_id, user.workspace_id)

    doc_sections: list[dict] = []
    approvals: list[dict] = []
    required = 2
    if proposal:
        doc_sections = db.get_sections(proposal["id"], user.workspace_id)
        approvals = db.get_approvals(proposal["id"], user.workspace_id)
        required = proposal.get("approvals_required", 2)

    state = submission.compute(
        confirm_open=readiness["confirm_open"],
        p0_blocking=readiness["p0_blocking"],
        sections_total=len(doc_sections),
        sections_placeholder=sum(1 for s in doc_sections if s.get("status") == "placeholder"),
        narrative_unapproved=sum(
            1 for s in doc_sections
            if s.get("kind") == "narrative" and not s.get("approved_at")
        ),
        approvals_done=len(approvals),
        approvals_required=required,
    )
    return ok({
        "stage": state.stage,
        "stage_label": state.stage_label,
        "completed_stages": state.completed_stages,
        "total_stages": state.total_stages,
        "percent": state.percent,
        "can_submit": state.can_submit,
        "blockers": [
            {"stage": b.stage, "label": b.label, "detail": b.detail} for b in state.blockers
        ],
    })


@router.post("/api/tenders/{tender_id}/prepare")
async def prepare(tender_id: str, user: CurrentUser) -> dict:
    if not db.get_tender(tender_id, user.workspace_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    # Lock + analyze + generate are blocking (DB + several model calls) — keep off the loop.
    return ok(await run_in_threadpool(_prepare, user.workspace_id, tender_id))
