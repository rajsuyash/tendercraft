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


def _readiness_payload(tenant_id: str, tender_id: str) -> dict:
    criteria = db.get_criteria(tender_id, tenant_id)
    analysis_result = db.get_analysis(tender_id, tenant_id)
    proposal = db.get_proposal_by_tender(tender_id, tenant_id)
    responses = db.get_responses(proposal["id"], tenant_id) if proposal else []
    decisions = db.get_readiness_decisions(tender_id, tenant_id)
    return compute_readiness(criteria, analysis_result, responses, decisions)


@router.get("/api/tenders/{tender_id}/readiness")
def get_readiness(tender_id: str, user: CurrentUser) -> dict:
    if not db.get_tender(tender_id, user.tenant_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    return ok(_readiness_payload(user.tenant_id, tender_id))


@router.put("/api/tenders/{tender_id}/criteria/{criterion_id}/decision")
def set_decision(tender_id: str, criterion_id: str, body: DecisionIn, user: CurrentUser) -> dict:
    """Record the bidder's per-item decision (resolve/ignore/do_not_proceed) + comment. Ignoring or
    dropping a P0 softens the deterministic block, so those decisions are audited."""
    # ET-6 + integrity: the criterion must belong to this tender AND this tenant before we write.
    if not db.get_criterion_in_tender(criterion_id, tender_id, user.tenant_id):
        raise ApiError(404, "CRITERION_NOT_FOUND", "criterion not found in this tender")
    # Audit BEFORE softening the gate: an override must never take effect without an audit trail.
    if body.decision in OVERRIDDEN_DECISIONS:
        db.write_audit(
            user.tenant_id, user.user_id, "readiness_decision", "criterion", criterion_id,
            after={"decision": body.decision},
        )
    db.upsert_readiness_decision(
        user.tenant_id, tender_id, criterion_id,
        decision=body.decision, comment=body.comment, actor=user.user_id,
    )
    return ok(_readiness_payload(user.tenant_id, tender_id))


def _prepare(tenant_id: str, tender_id: str) -> dict:
    from .proposal_routes import do_generate

    criteria = db.get_criteria(tender_id, tenant_id)
    # 1. Lock the TOM (human confirmation of low-confidence items is enforced by the gate).
    lock = evaluate_lock([_to_domain(c) for c in criteria])
    if not lock.ok:
        raise ApiError(409, "LOCK_BLOCKED", " | ".join(lock.blockers))
    db.set_tender_locked(tender_id, tenant_id, datetime.now(UTC).isoformat())

    # 2. Eligibility analysis (matches criteria against the structured profile).
    profile = db.get_profile_context(tenant_id)
    db.save_analysis(tenant_id, tender_id, analysis.analyze(criteria, profile))

    # 3. Draft-match against the content library.
    do_generate(tenant_id, tender_id)

    return _readiness_payload(tenant_id, tender_id)


@router.post("/api/tenders/{tender_id}/prepare")
async def prepare(tender_id: str, user: CurrentUser) -> dict:
    if not db.get_tender(tender_id, user.tenant_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    # Lock + analyze + generate are blocking (DB + several model calls) — keep off the loop.
    return ok(await run_in_threadpool(_prepare, user.tenant_id, tender_id))
