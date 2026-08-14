"""Tender + TOM endpoints (Module A). The lock endpoint runs the deterministic lock gate.

Every route scopes to the authenticated user's workspace (from the JWT, never the body).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import authz, db, spec_service
from .auth import AuthedUser, get_current_user
from .deterministic.lock import evaluate_lock
from .deterministic.tender_meta import display_title
from .deterministic.types import Criterion, RequirementLevel, SourceAnchor
from .envelope import ApiError, ok
from .ingest import (
    SourcePage,
    ingest_pages,
    number_package,
    parse_document_pages,
    parse_package_boq,
)

log = logging.getLogger("tendercraft.tenders")

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB guard


class ProjectIn(BaseModel):
    name: str


class ProjectPatch(BaseModel):
    name: str | None = None
    status: Literal["active", "won", "lost", "archived"] | None = None
    owner: str | None = None


class AssignProjectIn(BaseModel):
    project_id: str | None = None


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
    # Page alone is a resolvable anchor: real tenders state obligations in unnumbered
    # prose, and requiring a clause here silently produced anchor=None, which the lock
    # gate then refused forever (types.SourceAnchor.is_resolvable).
    if row.get("anchor_page"):
        anchor = SourceAnchor(page=row["anchor_page"], clause=row.get("anchor_clause") or "")
    return Criterion(
        id=row["id"],
        confidence=float(row["confidence"]),
        confirmed=bool(row["confirmed"]),
        requirement_level=RequirementLevel(row["requirement_level"]),
        anchor=anchor,
    )


def _relocate(row: dict, page_index: dict[int, SourcePage]) -> dict:
    """Rewrite a global package page back to the document and page a human can open.

    A criterion whose page fell outside the package keeps no anchor at all rather than a
    plausible wrong one — the lock gate refuses unanchored criteria (A-AC5), which is the
    correct outcome for an extraction nobody can check.
    """
    src = page_index.get(row.get("anchor_page") or 0)
    return {**row, "anchor_page": src.page if src else None,
            "anchor_document": src.document if src else None}


def _process_ingest(workspace_id: str, documents: list[tuple[str, bytes]], title: str) -> dict:
    """CPU/IO-bound ingest pipeline — run off the event loop via a threadpool."""
    source_pages: list[SourcePage] = []
    for filename, data in documents:
        source_pages.extend(parse_document_pages(filename, data))
    if not source_pages:
        raise ApiError(400, "BAD_DOCUMENT", "no readable pages in the uploaded package")
    pages, page_index = number_package(source_pages)
    result = ingest_pages(pages)
    result["criteria_rows"] = [_relocate(r, page_index) for r in result["criteria_rows"]]
    result["unmapped_rows"] = [
        {"sentence": r["sentence"],
         "page": page_index[r["page"]].page if r["page"] in page_index else None,
         "document": page_index[r["page"]].document if r["page"] in page_index else None}
        for r in result["unmapped_rows"]
    ]
    meta = result["meta"]
    # Name the bid after the TENDER, not the file. The filename survives only when the
    # document states no title of its own.
    tender = db.create_tender(workspace_id, display_title(meta, title))
    if meta.tender_number or meta.authority:
        db.set_tender_meta(tender["id"], workspace_id, meta.tender_number, meta.authority)
    # Keep the INSERTED rows: they carry the ids Module H binds a prose-derived line item
    # to. result["criteria_rows"] are pre-insert and have no id.
    inserted_criteria = (
        db.insert_criteria(workspace_id, tender["id"], result["criteria_rows"])
        if result["criteria_rows"] else []
    )
    # The denominator (G-FR2). Computed during ingest because page text is never persisted —
    # there is no later moment at which this could be recovered without a re-upload.
    if result["unmapped_rows"]:
        db.insert_unmapped(workspace_id, tender["id"], result["unmapped_rows"])
    # Module H: the schedule of items, from any spreadsheet in the package plus the technical
    # criteria just extracted. Non-fatal by construction — criteria extraction is the product
    # and a BOQ that cannot be read must never fail an upload (app/ingest.parse_package_boq
    # already swallows a bad workbook; this guards the persistence too).
    try:
        spec_service.persist_schedule(
            workspace_id, tender["id"], parse_package_boq(documents), inserted_criteria
        )
    except Exception:  # noqa: BLE001 — an addition must not be able to break ingest
        log.exception("schedule persistence failed for tender %s — ingest continues",
                      tender["id"])
    return {
        "tender_id": tender["id"],
        "title": display_title(meta, title),
        "tender_number": meta.tender_number,
        "authority": meta.authority,
        "pages": len(pages),
        "documents": [d for d, _ in documents],
        "extracted": result["extracted"],
        "low_confidence": result["low_confidence"],
        # Named where the user can find them: "Annexure-II.pdf p.4", not a package-wide count
        # that matches no page number printed on any document they hold.
        "illegible_pages": [
            f"{page_index[p].document} p.{page_index[p].page}"
            for p in result["illegible_pages"] if p in page_index
        ],
    }


@router.post("/api/tenders/ingest")
async def ingest_tender(
    user: CurrentUser, file: Annotated[list[UploadFile], File()], title: str = ""
) -> dict:
    """Ingest a tender PACKAGE — NIT, annexures and BOQ sheets — as one tender.

    The 50 MB ceiling is on the package, not per file: it exists to bound what one request
    can pull into memory, and ten files evade a per-file check entirely.
    """
    if not file:
        raise ApiError(400, "NO_FILE", "attach at least one document")
    documents: list[tuple[str, bytes]] = []
    total = 0
    for upload in file:
        # Reject oversize BEFORE reading the whole body into memory (DoS guard).
        if upload.size and total + upload.size > _MAX_UPLOAD_BYTES:
            raise ApiError(413, "FILE_TOO_LARGE", "tender package exceeds 50 MB")
        data = await upload.read()
        total += len(data)
        if total > _MAX_UPLOAD_BYTES:
            raise ApiError(413, "FILE_TOO_LARGE", "tender package exceeds 50 MB")
        documents.append((upload.filename or "Untitled document", data))
    name = title or documents[0][0] or "Untitled tender"
    # Parsing + extraction + inserts are blocking; keep the event loop free.
    return ok(await run_in_threadpool(_process_ingest, user.workspace_id, documents, name))


# Sync bodies (only blocking db calls) -> FastAPI runs them in a threadpool, off the loop.
@router.get("/api/projects")
def list_projects(user: CurrentUser) -> dict:
    return ok({"projects": db.list_projects(user.workspace_id)})


@router.post("/api/projects")
def create_project(body: ProjectIn, user: CurrentUser) -> dict:
    authz.check(user, authz.DRAFT)
    return ok(db.create_project(user.workspace_id, body.name, user.user_id))


@router.patch("/api/projects/{project_id}")
def update_project(project_id: str, body: ProjectPatch, user: CurrentUser) -> dict:
    authz.check(user, authz.DRAFT)
    if not db.get_project(project_id, user.workspace_id):
        raise ApiError(404, "PROJECT_NOT_FOUND", "project not found in your workspace")
    patch = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if patch:
        db.update_project(project_id, user.workspace_id, patch)
    return ok({"project_id": project_id, **patch})


@router.get("/api/tenders")
def list_tenders(
    user: CurrentUser,
    project_id: str | None = None,
    q: str | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 25,
) -> dict:
    """Portfolio list — filter, search, keyset pagination.

    Previously there was no list endpoint at all and the web page did .limit(50) with no
    cursor, so a workspace's 51st tender was permanently unreachable.
    """
    limit = max(1, min(limit, 100))
    rows = db.list_tenders(user.workspace_id, project_id=project_id, q=q, status=status,
                           cursor=cursor, limit=limit + 1)
    has_more = len(rows) > limit
    rows = rows[:limit]
    return ok({
        "tenders": rows,
        "next_cursor": db.make_cursor(rows[-1]) if (has_more and rows) else None,
    })


@router.put("/api/tenders/{tender_id}/project")
def assign_project(tender_id: str, body: AssignProjectIn, user: CurrentUser) -> dict:
    authz.check(user, authz.DRAFT)
    if not db.get_tender(tender_id, user.workspace_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    if body.project_id and not db.get_project(body.project_id, user.workspace_id):
        raise ApiError(404, "PROJECT_NOT_FOUND", "project not found in your workspace")
    db.set_tender_project(tender_id, user.workspace_id, body.project_id)
    return ok({"tender_id": tender_id, "project_id": body.project_id})


@router.post("/api/tenders")
def create_tender_route(body: CreateTender, user: CurrentUser) -> dict:
    tender = db.create_tender(user.workspace_id, body.title)
    return ok({"id": tender["id"], "status": tender["status"]})


@router.post("/api/tenders/{tender_id}/criteria")
def add_criteria(tender_id: str, body: list[CriterionIn], user: CurrentUser) -> dict:
    if not db.get_tender(tender_id, user.workspace_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    rows = db.insert_criteria(user.workspace_id, tender_id, [c.model_dump() for c in body])
    return ok(
        {
            "inserted": len(rows),
            "criteria": [{"id": r["id"], "confirmed": r["confirmed"]} for r in rows],
        }
    )


@router.post("/api/criteria/{criterion_id}/confirm")
def confirm(criterion_id: str, user: CurrentUser) -> dict:
    updated = db.confirm_criterion(criterion_id, user.workspace_id)
    if not updated:
        raise ApiError(404, "CRITERION_NOT_FOUND", "criterion not found in your workspace")
    return ok({"id": criterion_id, "confirmed": True})


@router.post("/api/tenders/{tender_id}/lock")
def lock(tender_id: str, user: CurrentUser) -> dict:
    if not db.get_tender(tender_id, user.workspace_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    rows = db.get_criteria(tender_id, user.workspace_id)
    result = evaluate_lock([_to_domain(r) for r in rows])
    if not result.ok:
        # deterministic gate refused — surface the exact blockers (A-AC5)
        raise ApiError(409, "LOCK_BLOCKED", " | ".join(result.blockers))
    db.set_tender_locked(tender_id, user.workspace_id, datetime.now(UTC).isoformat())
    return ok({"id": tender_id, "status": "locked", "criteria": len(rows)})
