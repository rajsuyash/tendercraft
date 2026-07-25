"""Analysis + profile endpoints (Module C). Analyze runs on a locked TOM only (A-FR5)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from . import analysis, db, estimator, rubric_service
from .auth import AuthedUser, get_current_user
from .envelope import ApiError, ok

_CATEGORY_CLUSTER = "it-hardware"  # v0: single category cluster until classification lands

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


@router.get("/api/profile")
def get_profile(user: CurrentUser) -> dict:
    return ok(db.get_profile_context(user.workspace_id))


@router.post("/api/tenders/{tender_id}/analyze")
def run_analysis(tender_id: str, user: CurrentUser) -> dict:
    tender = db.get_tender(tender_id, user.workspace_id)
    if not tender:
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    if tender.get("status") != "locked":
        # A-FR5: only a locked TOM is a stable basis for deterministic compliance
        raise ApiError(409, "TOM_NOT_LOCKED", "lock the TOM before running eligibility analysis")
    criteria = db.get_criteria(tender_id, user.workspace_id)
    profile = db.get_profile_context(user.workspace_id)
    result = analysis.analyze(criteria, profile)
    db.save_analysis(user.workspace_id, tender_id, result)
    return ok(result)


@router.get("/api/tenders/{tender_id}/analysis")
def get_analysis(tender_id: str, user: CurrentUser) -> dict:
    result = db.get_analysis(tender_id, user.workspace_id)
    if result is None:
        raise ApiError(404, "NO_ANALYSIS", "run eligibility analysis first")
    return ok(result)


def _rubric_for(tender_id: str, user: CurrentUser):
    proposal = db.get_proposal_by_tender(tender_id, user.workspace_id)
    if not proposal:
        raise ApiError(404, "NO_PROPOSAL", "generate a proposal first")
    doc_sections = db.get_sections(proposal["id"], user.workspace_id)
    if not doc_sections:
        raise ApiError(409, "NO_SECTIONS", "generate the proposal document first")
    return proposal, rubric_service.compute(
        doc_sections,
        db.get_criteria(tender_id, user.workspace_id),
        db.get_profile_context(user.workspace_id),
        db.get_valid_library_docs(user.workspace_id, datetime.now(UTC).date().isoformat()),
    )


@router.post("/api/tenders/{tender_id}/rubric")
def run_rubric(tender_id: str, user: CurrentUser) -> dict:
    """Score the DOCUMENT on technical competence.

    Never suppressed, unlike /estimate: this measures an artifact we fully observe rather
    than predicting an external committee, so it needs no historical outcomes (D-AC4 does
    not apply). See app/deterministic/rubric.py for why the two stay separate.
    """
    if not db.get_tender(tender_id, user.workspace_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    _proposal, result = _rubric_for(tender_id, user)
    return ok(rubric_service.payload(result))


@router.post("/api/tenders/{tender_id}/estimate")
def run_estimate(tender_id: str, user: CurrentUser) -> dict:
    tender = db.get_tender(tender_id, user.workspace_id)
    if not tender:
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    analysis_result = db.get_analysis(tender_id, user.workspace_id)
    if analysis_result is None:
        raise ApiError(409, "NO_ANALYSIS", "run eligibility analysis before estimating a score")
    cluster = tender.get("authority") or "unknown"
    count = db.count_cluster_outcomes(user.workspace_id, cluster, _CATEGORY_CLUSTER)

    # Feed the measured document quality in, so the prediction is no longer based purely on
    # a pre-drafting eligibility pass-rate that never read the proposal.
    rubric_total = None
    try:
        _proposal, r = _rubric_for(tender_id, user)
        rubric_total = r.total
    except ApiError:
        pass  # no document yet — fall back to the eligibility-only basis

    result = estimator.estimate(count, analysis_result, rubric_total=rubric_total)
    db.save_estimate(user.workspace_id, tender_id, result)
    return ok(result)


@router.get("/api/tenders/{tender_id}/estimate")
def get_estimate(tender_id: str, user: CurrentUser) -> dict:
    result = db.get_estimate(tender_id, user.workspace_id)
    if result is None:
        raise ApiError(404, "NO_ESTIMATE", "run a score estimate first")
    return ok(result)
