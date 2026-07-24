"""Tender + TOM endpoints (Module A). The lock endpoint runs the deterministic lock gate.

Every route scopes to the authenticated user's tenant (from the JWT, never the body).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import db
from .auth import AuthedUser, get_current_user
from .deterministic.lock import evaluate_lock
from .deterministic.types import Criterion, RequirementLevel, SourceAnchor
from .envelope import ApiError, ok

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


class CreateTender(BaseModel):
    title: str = Field(min_length=1, max_length=500)


class CriterionIn(BaseModel):
    verbatim_text: str
    category: str
    requirement_level: str
    confidence: float = Field(ge=0, le=1)
    confirmed: bool = False
    anchor_page: int | None = None
    anchor_clause: str | None = None
    evidence_required: str | None = None
    evaluation_weight: float | None = None


def _to_domain(row: dict) -> Criterion:
    anchor = None
    if row.get("anchor_page") and row.get("anchor_clause"):
        anchor = SourceAnchor(page=row["anchor_page"], clause=row["anchor_clause"])
    return Criterion(
        id=row["id"],
        confidence=float(row["confidence"]),
        confirmed=bool(row["confirmed"]),
        requirement_level=RequirementLevel(row["requirement_level"]),
        anchor=anchor,
    )


@router.post("/api/tenders")
async def create_tender(body: CreateTender, user: CurrentUser) -> dict:
    tender = db.create_tender(user.tenant_id, body.title)
    return ok({"id": tender["id"], "status": tender["status"]})


@router.post("/api/tenders/{tender_id}/criteria")
async def add_criteria(tender_id: str, body: list[CriterionIn], user: CurrentUser) -> dict:
    if not db.get_tender(tender_id, user.tenant_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    rows = db.insert_criteria(user.tenant_id, tender_id, [c.model_dump() for c in body])
    return ok(
        {
            "inserted": len(rows),
            "criteria": [{"id": r["id"], "confirmed": r["confirmed"]} for r in rows],
        }
    )


@router.post("/api/criteria/{criterion_id}/confirm")
async def confirm(criterion_id: str, user: CurrentUser) -> dict:
    updated = db.confirm_criterion(criterion_id, user.tenant_id)
    if not updated:
        raise ApiError(404, "CRITERION_NOT_FOUND", "criterion not found in your workspace")
    return ok({"id": criterion_id, "confirmed": True})


@router.post("/api/tenders/{tender_id}/lock")
async def lock(tender_id: str, user: CurrentUser) -> dict:
    if not db.get_tender(tender_id, user.tenant_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    rows = db.get_criteria(tender_id, user.tenant_id)
    result = evaluate_lock([_to_domain(r) for r in rows])
    if not result.ok:
        # deterministic gate refused — surface the exact blockers (A-AC5)
        raise ApiError(409, "LOCK_BLOCKED", " | ".join(result.blockers))
    db.set_tender_locked(tender_id, user.tenant_id, datetime.now(UTC).isoformat())
    return ok({"id": tender_id, "status": "locked", "criteria": len(rows)})
