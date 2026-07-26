"""Knowledge-base ingestion endpoint — add company docs (file) or a website (URL) to the library."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from . import db, knowledge
from .auth import AuthedUser, get_current_user
from .deterministic.drafting import template_placeholders
from .envelope import ApiError, ok

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _ingest_text(
    workspace_id: str, actor: str, text: str,
    criterion_id: str | None = None, tender_id: str | None = None,
) -> dict:
    doc = knowledge.build_document(text)
    row = db.insert_library_document(workspace_id, doc, actor)
    # If the upload targets a specific readiness item, link the doc to it (keeps any prior
    # decision — attaching evidence doesn't reset an ignore/do-not-proceed choice).
    if criterion_id and tender_id:
        db.upsert_readiness_decision(
            workspace_id, tender_id, criterion_id, document_id=row["id"], actor=actor,
        )
    return {
        "id": row["id"], "name": row["name"],
        "doc_type": row["doc_type"], "valid_to": row.get("valid_to"),
    }


@router.post("/api/knowledge/ingest")
async def ingest_knowledge(
    user: CurrentUser,
    file: Annotated[UploadFile | None, File()] = None,
    url: Annotated[str | None, Form()] = None,
    criterion_id: Annotated[str | None, Form()] = None,
    tender_id: Annotated[str | None, Form()] = None,
) -> dict:
    """Ingest one source (a file OR a url) into the knowledge base. Optional criterion_id +
    tender_id link the resulting document to a specific readiness item."""
    # If linking to an item, both ids are required and the criterion must belong to this tender
    # AND this workspace — validate BEFORE any work (ET-6: the engine bypasses RLS).
    if (criterion_id is None) != (tender_id is None):
        raise ApiError(400, "BAD_LINK", "criterion_id and tender_id must be provided together")
    if criterion_id and tender_id:
        owned = await run_in_threadpool(
            db.get_criterion_in_tender, criterion_id, tender_id, user.workspace_id,
        )
        if not owned:
            raise ApiError(404, "CRITERION_NOT_FOUND", "criterion not found in this tender")

    if file is not None:
        # Read with a hard ceiling regardless of a (possibly-absent/spoofed) content-length.
        data = await file.read(_MAX_UPLOAD_BYTES + 1)
        if len(data) > _MAX_UPLOAD_BYTES:
            raise ApiError(413, "FILE_TOO_LARGE", "document exceeds 25 MB")
        text = await run_in_threadpool(knowledge.extract_text, file.filename or "upload", data)
    elif url:
        text = await run_in_threadpool(knowledge.fetch_url_text, url)
    else:
        raise ApiError(400, "NO_SOURCE", "provide a file or a url")

    if not text.strip():
        raise ApiError(422, "NO_TEXT", "no readable text found in the source")

    result = await run_in_threadpool(
        _ingest_text, user.workspace_id, user.user_id, text, criterion_id, tender_id,
    )
    # A document still carrying "[Insert Designation]" is a blank form, not evidence — and
    # the retriever will hand it to the drafter as prose, which then quotes it WITH a
    # citation. That is exactly how "Merdian Technology" reached a government submission.
    return ok({**result, "template_placeholders": template_placeholders(text)})
