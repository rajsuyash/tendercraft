"""Proposal generation + retrieval endpoints (Module B). Generation runs on a locked TOM."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from pipeline.drafter import draft_response
from pipeline.retrieval import select_evidence

from . import db
from .auth import AuthedUser, get_current_user
from .deterministic.drafting import mandatory_coverage
from .envelope import ApiError, ok

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


@router.get("/api/library")
def list_library(user: CurrentUser) -> dict:
    today = datetime.now(UTC).date().isoformat()
    docs = db.get_valid_library_docs(user.tenant_id, today)
    return ok({"documents": docs, "count": len(docs)})


def do_generate(tenant_id: str, tender_id: str) -> dict:
    """Draft every criterion from the library and persist responses. Caller ensures the TOM
    is locked. Reused by both /generate and the readiness /prepare orchestration."""
    criteria = db.get_criteria(tender_id, tenant_id)
    today = datetime.now(UTC).date().isoformat()
    evidence = db.get_valid_library_docs(tenant_id, today)
    chunks = [
        {"id": d["id"], "name": d["name"], "text": d.get("text_content", "")} for d in evidence
    ]
    # A doc the bidder attached to a specific item pins that item's evidence (reliable cites).
    pinned_by = {
        d["criterion_id"]: d.get("document_id")
        for d in db.get_readiness_decisions(tender_id, tenant_id)
        if d.get("document_id")
    }

    proposal = db.create_proposal(tenant_id, tender_id)

    # Draft all criteria concurrently — each is an independent model call; sequential would
    # blow the request budget on a large tender (retry cap keeps cost bounded per call). Each
    # criterion sees only its selected evidence (pinned doc or top-K relevant), not the whole pile.
    def _draft(c: dict):
        ev = select_evidence(c["verbatim_text"], chunks, pinned_by.get(c["id"]))
        return draft_response(c["verbatim_text"], ev)

    with ThreadPoolExecutor(max_workers=6) as pool:
        drafts = list(pool.map(_draft, criteria))

    coverage_rows: list[dict] = []
    total_flags = 0
    for c, drafted in zip(criteria, drafts, strict=True):
        db.upsert_response(
            tenant_id, proposal["id"], c["id"],
            {
                "draft_text": drafted.draft_text,
                "sentences": drafted.sentences,
                "draft_status": drafted.draft_status,
                "flags": drafted.flags,
            },
        )
        total_flags += len(drafted.flags)
        coverage_rows.append(
            {"requirement_level": c["requirement_level"], "draft_status": drafted.draft_status}
        )

    return {
        "proposal_id": proposal["id"],
        "responses": len(criteria),
        "mandatory_coverage": mandatory_coverage(coverage_rows),
        "open_flags": total_flags,
    }


@router.post("/api/tenders/{tender_id}/generate")
def generate_proposal(tender_id: str, user: CurrentUser) -> dict:
    tender = db.get_tender(tender_id, user.tenant_id)
    if not tender:
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    if tender.get("status") != "locked":
        raise ApiError(409, "TOM_NOT_LOCKED", "lock the TOM before generating a proposal")
    return ok(do_generate(user.tenant_id, tender_id))


@router.get("/api/tenders/{tender_id}/proposal")
def get_proposal(tender_id: str, user: CurrentUser) -> dict:
    proposal = db.get_proposal_by_tender(tender_id, user.tenant_id)
    if not proposal:
        raise ApiError(404, "NO_PROPOSAL", "generate a proposal first")
    responses = db.get_responses(proposal["id"], user.tenant_id)
    return ok({"proposal": proposal, "responses": responses})


def _load_export_context(tender_id: str, user: CurrentUser):
    from . import export_service

    proposal = db.get_proposal_by_tender(tender_id, user.tenant_id)
    if not proposal:
        raise ApiError(404, "NO_PROPOSAL", "generate a proposal first")
    criteria = db.get_criteria(tender_id, user.tenant_id)
    responses = db.get_responses(proposal["id"], user.tenant_id)
    approvals = db.get_approvals(proposal["id"], user.tenant_id)
    return export_service, proposal, criteria, responses, approvals


def _matrix_payload(decision, rows) -> dict:
    return {
        "exportable": decision.exportable,
        "hard_blockers": list(decision.hard_blockers),
        "override_blockers": list(decision.override_blockers),
        "override_used": decision.override_used,
        "mandatory_coverage": decision.resolved_mandatory_fraction,
        "rows": [
            {
                "criterion_id": r.criterion_id,
                "requirement_level": r.requirement_level.value,
                "status": r.status.value,
                "has_uncited_financial_claim": r.has_uncited_financial_claim,
            }
            for r in rows
        ],
    }


@router.get("/api/tenders/{tender_id}/compliance-matrix")
def compliance_matrix(tender_id: str, user: CurrentUser) -> dict:
    export_service, proposal, criteria, responses, approvals = _load_export_context(tender_id, user)
    decision, rows = export_service.evaluate(
        criteria, responses, proposal.get("approvals_required", 2), len(approvals)
    )
    return ok({**_matrix_payload(decision, rows), "approvals": approvals,
               "approvals_required": proposal.get("approvals_required", 2)})


@router.post("/api/proposals/{proposal_id}/approve")
def approve(proposal_id: str, user: CurrentUser, stage: str = "review") -> dict:
    db.add_approval(user.tenant_id, proposal_id, stage, user.user_id)
    db.write_audit(user.tenant_id, user.user_id, "approval", "proposal", proposal_id,
                   after={"stage": stage})
    return ok({"proposal_id": proposal_id, "stage": stage})


@router.post("/api/tenders/{tender_id}/export")
def export_proposal(tender_id: str, user: CurrentUser, override: bool = False) -> dict:
    export_service, proposal, criteria, responses, approvals = _load_export_context(tender_id, user)
    decision, rows = export_service.evaluate(
        criteria, responses, proposal.get("approvals_required", 2), len(approvals),
        admin_override=override,
    )
    if not decision.exportable:
        blockers = list(decision.hard_blockers) + list(decision.override_blockers)
        raise ApiError(409, "EXPORT_BLOCKED", " | ".join(blockers))

    from datetime import UTC, datetime

    when = datetime.now(UTC).isoformat()
    db.mark_exported(proposal["id"], user.tenant_id, when)
    db.write_audit(user.tenant_id, user.user_id, "export", "proposal", proposal["id"],
                   after={"override_used": decision.override_used})
    return ok({"proposal_id": proposal["id"], "exported_at": when,
               "override_used": decision.override_used})
