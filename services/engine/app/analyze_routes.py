"""Analysis + profile endpoints (Module C). Analyze runs on a locked TOM only (A-FR5)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from . import analysis, db, estimator
from .auth import AuthedUser, get_current_user
from .envelope import ApiError, ok

_CATEGORY_CLUSTER = "it-hardware"  # v0: single category cluster until classification lands

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


@router.get("/api/profile")
def get_profile(user: CurrentUser) -> dict:
    return ok(db.get_profile_context(user.tenant_id))


@router.post("/api/tenders/{tender_id}/analyze")
def run_analysis(tender_id: str, user: CurrentUser) -> dict:
    tender = db.get_tender(tender_id, user.tenant_id)
    if not tender:
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    if tender.get("status") != "locked":
        # A-FR5: only a locked TOM is a stable basis for deterministic compliance
        raise ApiError(409, "TOM_NOT_LOCKED", "lock the TOM before running eligibility analysis")
    criteria = db.get_criteria(tender_id, user.tenant_id)
    profile = db.get_profile_context(user.tenant_id)
    result = analysis.analyze(criteria, profile)
    db.save_analysis(user.tenant_id, tender_id, result)
    return ok(result)


@router.get("/api/tenders/{tender_id}/analysis")
def get_analysis(tender_id: str, user: CurrentUser) -> dict:
    result = db.get_analysis(tender_id, user.tenant_id)
    if result is None:
        raise ApiError(404, "NO_ANALYSIS", "run eligibility analysis first")
    return ok(result)


@router.post("/api/tenders/{tender_id}/estimate")
def run_estimate(tender_id: str, user: CurrentUser) -> dict:
    tender = db.get_tender(tender_id, user.tenant_id)
    if not tender:
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    analysis_result = db.get_analysis(tender_id, user.tenant_id)
    if analysis_result is None:
        raise ApiError(409, "NO_ANALYSIS", "run eligibility analysis before estimating a score")
    cluster = tender.get("authority") or "unknown"
    count = db.count_cluster_outcomes(user.tenant_id, cluster, _CATEGORY_CLUSTER)
    result = estimator.estimate(count, analysis_result)
    db.save_estimate(user.tenant_id, tender_id, result)
    return ok(result)


@router.get("/api/tenders/{tender_id}/estimate")
def get_estimate(tender_id: str, user: CurrentUser) -> dict:
    result = db.get_estimate(tender_id, user.tenant_id)
    if result is None:
        raise ApiError(404, "NO_ESTIMATE", "run a score estimate first")
    return ok(result)
