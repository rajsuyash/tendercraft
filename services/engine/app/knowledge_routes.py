"""Knowledge-base ingestion endpoint — add company docs (file) or a website (URL) to the library."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from . import db, knowledge
from .auth import AuthedUser, get_current_user
from .envelope import ApiError, ok

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _ingest_text(tenant_id: str, actor: str, text: str) -> dict:
    doc = knowledge.build_document(text)
    row = db.insert_library_document(tenant_id, doc, actor)
    return {
        "id": row["id"], "name": row["name"],
        "doc_type": row["doc_type"], "valid_to": row.get("valid_to"),
    }


@router.post("/api/knowledge/ingest")
async def ingest_knowledge(
    user: CurrentUser,
    file: Annotated[UploadFile | None, File()] = None,
    url: Annotated[str | None, Form()] = None,
) -> dict:
    """Ingest one source (a file OR a url) into the knowledge base."""
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

    result = await run_in_threadpool(_ingest_text, user.tenant_id, user.user_id, text)
    return ok(result)
