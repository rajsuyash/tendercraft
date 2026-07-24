"""Proposal generation + retrieval endpoints (Module B). Generation runs on a locked TOM."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from pipeline.drafter import draft_response

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


@router.post("/api/tenders/{tender_id}/generate")
def generate_proposal(tender_id: str, user: CurrentUser) -> dict:
    tender = db.get_tender(tender_id, user.tenant_id)
    if not tender:
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    if tender.get("status") != "locked":
        raise ApiError(409, "TOM_NOT_LOCKED", "lock the TOM before generating a proposal")

    criteria = db.get_criteria(tender_id, user.tenant_id)
    today = datetime.now(UTC).date().isoformat()
    evidence = db.get_valid_library_docs(user.tenant_id, today)
    chunks = [
        {"id": d["id"], "name": d["name"], "text": d.get("text_content", "")} for d in evidence
    ]

    proposal = db.create_proposal(user.tenant_id, tender_id)

    # Draft all criteria concurrently — each is an independent model call; sequential would
    # blow the request budget on a large tender (retry cap keeps cost bounded per call).
    with ThreadPoolExecutor(max_workers=6) as pool:
        drafts = list(pool.map(lambda c: draft_response(c["verbatim_text"], chunks), criteria))

    coverage_rows: list[dict] = []
    total_flags = 0
    for c, drafted in zip(criteria, drafts, strict=True):
        db.upsert_response(
            user.tenant_id, proposal["id"], c["id"],
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

    coverage = mandatory_coverage(coverage_rows)
    return ok(
        {
            "proposal_id": proposal["id"],
            "responses": len(criteria),
            "mandatory_coverage": coverage,
            "open_flags": total_flags,
        }
    )


@router.get("/api/tenders/{tender_id}/proposal")
def get_proposal(tender_id: str, user: CurrentUser) -> dict:
    proposal = db.get_proposal_by_tender(tender_id, user.tenant_id)
    if not proposal:
        raise ApiError(404, "NO_PROPOSAL", "generate a proposal first")
    responses = db.get_responses(proposal["id"], user.tenant_id)
    return ok({"proposal": proposal, "responses": responses})
