"""Past bids — the client's own submitted proposals, mined into an answer library (G-FR3).

A past proposal dropped into the content library today is undifferentiated evidence prose: the
retriever hands it to the drafter, which quotes it and attaches a citation. Nothing records
which requirement an answer answered, or whether the bid won. This endpoint is where a finished
Word document stops being a blob and becomes reusable, attributable answers.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from . import authz, db
from .auth import AuthedUser, get_current_user
from .deterministic.answer_mining import mine_answers
from .deterministic.drafting import template_placeholders
from .envelope import ApiError, ok
from .ingest import parse_document_pages
from .sections import SECTION_SPECS

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # the package ceiling, matching tender ingest
_MAX_DOC_CHARS = 20000  # library_documents.text_content is stored truncated

#: (key, heading) pairs for section matching. Passed into the deterministic miner rather than
#: imported by it, so app/deterministic/ stays free of app-level imports.
_SPECS = tuple((s.key, s.heading) for s in SECTION_SPECS)


class OutcomeIn(BaseModel):
    outcome: Literal["won", "lost", "unknown"]


def _process(
    workspace_id: str, actor: str, documents: list[tuple[str, bytes]], meta: dict,
) -> dict:
    pages: list[tuple[str, str]] = []
    for filename, data in documents:
        pages.extend((p.document, p.text) for p in parse_document_pages(filename, data))
    text = "\n".join(t for _, t in pages).strip()
    if not text:
        raise ApiError(422, "NO_TEXT", "no readable text found in this bid")

    # A document still carrying "[Insert Designation]" is a blank form, not a submitted bid.
    # Mining it would seed the answer library with template prose that later reaches a draft
    # WITH a citation attached — which is exactly how "Merdian Technology" reached a real
    # government submission (docs/known-pitfalls.md). Refuse before storing anything.
    markers = template_placeholders(text)
    if markers:
        raise ApiError(
            422, "UNFILLED_TEMPLATE",
            "this looks like a blank form rather than a submitted bid — it still contains "
            + ", ".join(markers),
        )

    doc = db.insert_library_document(
        workspace_id,
        {
            "name": meta["name"],
            "doc_type": "past_proposal",
            "text_content": text[:_MAX_DOC_CHARS],
            "valid_to": None,  # a submitted bid never expires; the CLAIMS inside it do
            "structured_fields": {},
        },
        actor,
    )
    bid = db.create_past_bid(
        workspace_id,
        {
            "name": meta["name"],
            "authority": meta.get("authority"),
            "tender_number": meta.get("tender_number"),
            "submitted_on": meta.get("submitted_on"),
            "outcome": meta.get("outcome") or "unknown",
            "source_document_id": doc["id"],
        },
        actor,
    )

    mined = mine_answers(pages, _SPECS)
    stored = db.upsert_answers(workspace_id, bid["id"], [
        {
            "requirement_text": m.requirement_text,
            "answer_text": m.answer_text,
            "section_key": m.section_key,
            "mined_by": m.mined_by,
        }
        for m in mined
    ])
    db.write_audit(workspace_id, actor, "past_bid_ingested", "past_bid", bid["id"],
                   after={"name": bid["name"], "answers": len(stored)})
    return {
        "id": bid["id"],
        "name": bid["name"],
        "outcome": bid["outcome"],
        "documents": [d for d, _ in documents],
        "answers_mined": len(stored),
        # Named so the user can judge the mining rather than trust it.
        "sections_recognised": sorted({m.section_key for m in mined if m.section_key}),
    }


@router.post("/api/past-bids")
async def ingest_past_bid(
    user: CurrentUser,
    file: Annotated[list[UploadFile], File()],
    name: Annotated[str, Form()] = "",
    authority: Annotated[str | None, Form()] = None,
    tender_number: Annotated[str | None, Form()] = None,
    submitted_on: Annotated[str | None, Form()] = None,
    outcome: Annotated[str, Form()] = "unknown",
) -> dict:
    """Upload one submitted bid (its whole package) and mine it into answers.

    `outcome` is user-supplied and never inferred: we cannot see an award notice, and a
    guessed win would quietly rank what every future proposal reuses.
    """
    authz.check(user, authz.UPLOAD)
    if not file:
        raise ApiError(400, "NO_FILE", "attach at least one document")
    if outcome not in ("won", "lost", "unknown"):
        raise ApiError(400, "BAD_OUTCOME", "outcome must be won, lost or unknown")
    if submitted_on:
        try:
            date.fromisoformat(submitted_on)
        except ValueError as exc:
            raise ApiError(400, "BAD_DATE", "submitted_on must be YYYY-MM-DD") from exc

    documents: list[tuple[str, bytes]] = []
    total = 0
    for upload in file:
        if upload.size and total + upload.size > _MAX_UPLOAD_BYTES:
            raise ApiError(413, "FILE_TOO_LARGE", "bid package exceeds 50 MB")
        data = await upload.read()
        total += len(data)
        if total > _MAX_UPLOAD_BYTES:
            raise ApiError(413, "FILE_TOO_LARGE", "bid package exceeds 50 MB")
        documents.append((upload.filename or "Untitled document", data))

    meta = {
        "name": name or documents[0][0],
        "authority": authority,
        "tender_number": tender_number,
        "submitted_on": submitted_on,
        "outcome": outcome,
    }
    return ok(await run_in_threadpool(_process, user.workspace_id, user.user_id, documents, meta))


@router.get("/api/past-bids")
def list_past_bids(user: CurrentUser) -> dict:
    bids = db.list_past_bids(user.workspace_id)
    return ok({"past_bids": bids, "count": len(bids)})


@router.patch("/api/past-bids/{past_bid_id}")
def set_outcome(past_bid_id: str, body: OutcomeIn, user: CurrentUser) -> dict:
    """Correct a bid's outcome — usually months later, when the award is finally published."""
    authz.check(user, authz.DRAFT)
    bid = db.get_past_bid(past_bid_id, user.workspace_id)
    if not bid:
        raise ApiError(404, "PAST_BID_NOT_FOUND", "past bid not found in your workspace")
    db.set_past_bid_outcome(past_bid_id, user.workspace_id, body.outcome)
    db.write_audit(
        user.workspace_id, user.user_id, "past_bid_outcome_set", "past_bid", past_bid_id,
        before={"outcome": bid.get("outcome")}, after={"outcome": body.outcome},
    )
    return ok({"id": past_bid_id, "outcome": body.outcome,
               "updated_at": datetime.now(UTC).isoformat()})
