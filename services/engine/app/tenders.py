"""Tender + TOM endpoints (Module A). The lock endpoint runs the deterministic lock gate.

Every route scopes to the authenticated user's workspace (from the JWT, never the body).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import authz, db, ocr, spec_service
from .auth import AuthedUser, get_current_user
from .deterministic.lock import evaluate_lock
from .deterministic.tender_meta import TenderMeta, display_title, extract_tender_meta
from .deterministic.types import Criterion, RequirementLevel, SourceAnchor
from .envelope import ApiError, ok
from .ingest import (
    MIN_CHARS_PER_PAGE,
    SourcePage,
    ingest_pages,
    number_package,
    parse_document_pages,
    parse_package_boq,
)

log = logging.getLogger("tendercraft.tenders")

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB guard

#: What a tender is called when nothing — not the document, not the filename — said what it is.
#: `display_title` produces this string and two backfills test for it; a literal in three places
#: is a rename waiting to go unnoticed.
PLACEHOLDER_TITLE = "Untitled tender"


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


class TenderPatch(BaseModel):
    # 300 chars: the column is `text`, the cap is a UI decision (a heading, not a body).
    title: str = Field(min_length=1, max_length=300)


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


def _rename_if_placeholder(
    workspace_id: str, tender_id: str, meta: TenderMeta, current_title: str,
) -> str | None:
    """Replace the placeholder title once something learns what the tender is actually called.

    ONLY the placeholder. A parsed title, or a filename a human chose, must never be replaced
    by a backfill — that rule is the whole content of this function, and it now has two
    callers that learn the same facts from different places: the pursuit backfill (number and
    authority from the portal listing) and the OCR pass (a cover page that was a scan at
    ingest time). Two copies of "rename only when…" is how the two drift apart.

    Returns the new title, or None when nothing was renamed.

    Mirror: `ReadinessHub.tsx`'s subtitle-dedup block rebuilds `display_title`'s
    "number · authority" join in TypeScript to compare against the string this produced.
    """
    if current_title != PLACEHOLDER_TITLE:
        return None
    renamed = display_title(meta, PLACEHOLDER_TITLE)
    if renamed == PLACEHOLDER_TITLE:
        return None
    db.set_tender_title(tender_id, workspace_id, renamed)
    return renamed


def _apply_pursuit_context(
    workspace_id: str, pursuit_id: str, tender_id: str,
    tender_number: str, authority: str, current_title: str = "",
) -> None:
    """Link the pursuit to the tender it produced, and fill in what the document did not state.

    Precedence is DOCUMENT FIRST, deliberately. The uploaded package is the legal artefact and
    `extract_meta`/`display_title` already prefer it; the feed row is a portal listing *about*
    that document. Only where the document is silent does the portal's own published reference
    fill the gap — and it is a value the portal published, never an inference.

    Non-fatal by construction, matching the schedule-persistence call below it: a pursuit that
    cannot be read must never fail an upload. The package is the product; the link is
    bookkeeping, and bookkeeping that can break ingest is worse than no bookkeeping.
    """
    try:
        pursuit = db.get_pursuit(workspace_id, pursuit_id)
        if pursuit is None:
            # Not an error the user can act on, and not a reason to lose their upload. Logged
            # because a rising count here means the feed and the pursuit table disagree.
            log.warning("pursuit %s not found in workspace %s — tender %s ingested unlinked",
                        pursuit_id, workspace_id, tender_id)
            return
        opp = pursuit.get("opportunities") or {}
        number = tender_number or opp.get("portal_ref_no") or ""
        auth = authority or opp.get("authority") or ""
        if number or auth:
            db.set_tender_meta(tender_id, workspace_id, number, auth)
            # display_title() ran BEFORE this backfill learned the opportunity's number and
            # authority, so a scanned package can be stamped "Untitled tender" and gain a
            # number a moment later — otherwise the readiness header keeps the placeholder
            # forever while the line beneath it names the tender.
            _rename_if_placeholder(
                workspace_id, tender_id,
                TenderMeta(tender_number=number or None, authority=auth or None),
                current_title,
            )
        db.link_pursuit_tender(workspace_id, pursuit_id, tender_id)
    except Exception:  # noqa: BLE001 — an addition must not be able to break ingest
        log.exception("pursuit linking failed for tender %s — ingest continues", tender_id)


def _process_ingest(workspace_id: str, documents: list[tuple[str, bytes]], title: str,
                    pursuit_id: str = "") -> dict:
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
    stored_title = display_title(meta, title)
    tender = db.create_tender(workspace_id, stored_title)
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
    if pursuit_id:
        # After the tender and its criteria exist: the link should point at a tender that is
        # actually usable, not one that may still fail mid-ingest.
        _apply_pursuit_context(workspace_id, pursuit_id, tender["id"],
                               meta.tender_number or "", meta.authority or "",
                               current_title=stored_title)
    return {
        "tender_id": tender["id"],
        "title": stored_title,
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


def _extract_quietly(workspace_id: str, tender_id: str) -> None:
    """Read the schedule's specifications. A failure here never reaches the uploader.

    The upload has already succeeded and been reported by the time this runs. Losing an
    optional read of the schedule must not turn that into an error the user cannot act on —
    same reasoning as `learning.harvest_quietly` on the export path.
    """
    # ponytail: no jobs table. Cloud Run throttles CPU once the response is flushed
    # (--no-cpu-throttling is not set), so a queued read can STALL until the next request
    # wakes the instance — min-instances is 1 on the engine (measured 2026-09-14; the 0 in
    # docs/deploy.md is stale), so it is rarely lost outright. State stays honest either
    # way: specs_extracted_at remains NULL and the manual button covers it. Add a jobs
    # table if stalled reads start showing up in the logs.
    try:
        items = db.get_line_items(tender_id, workspace_id)
        if items:
            counts = spec_service.extract_schedule(workspace_id, items)
            log.info("schedule specs read for tender %s: %s", tender_id, counts)
            if counts["skipped"]:
                # The stamp means a COMPLETE read (see spec_routes.extract_schedule for the
                # same rule on the manual button). Leave it NULL rather than tell the fit
                # screen "no specification" about lines this pass never reached.
                log.warning(
                    "schedule read INCOMPLETE for tender %s: %s of %s distinct descriptions, "
                    "budget %s", tender_id, counts["read"], counts["distinct"],
                    counts["budget"],
                )
            else:
                db.mark_specs_extracted(workspace_id, tender_id)
        else:
            db.mark_specs_extracted(workspace_id, tender_id)
    except Exception:  # noqa: BLE001 — deliberate: never fail an upload that already returned
        log.exception("background spec extraction failed for tender %s", tender_id)


def _ocr_package(
    documents: list[tuple[str, bytes]],
) -> tuple[list[SourcePage], set[int]]:
    """Re-read the package, OCR'ing every page that fell under the legibility floor.

    Returns the package's pages with recovered text folded in, and the GLOBAL page numbers OCR
    actually recovered.

    The numbering is rebuilt exactly the way ingest built it — `parse_document_pages` is
    deterministic over the same bytes, in the same order — so a criterion anchored here names
    the same page a human already saw on the recent-uploads list. Re-parsing is cheap (pypdf,
    no model, no network); carrying a page index across a request boundary would not be.

    The budget is `ocr.MAX_PAGES` for the WHOLE PACKAGE, not per document. `ocr_pdf_pages`
    caps each call at that number, so a package of ten scanned annexures would otherwise fan
    out to ten times the cap — and every recovered page costs one model call downstream. A
    truncation is logged rather than silently taken: a partial OCR that looks complete is the
    capped-sweep failure this codebase keeps rediscovering.
    """
    pages: list[SourcePage] = []
    recovered_globals: set[int] = set()
    budget = ocr.MAX_PAGES
    scanned_total = 0

    for filename, data in documents:
        parsed = parse_document_pages(filename, data)
        offset = len(pages)          # global page number of parsed[0] is offset + 1
        pages.extend(parsed)
        if filename.lower().rsplit(".", 1)[-1] != "pdf":
            continue                 # a spreadsheet page with no text has no image to read
        # Exactly the pages ingest dropped — same constant, imported rather than restated.
        scanned = [p.page for p in parsed if len(p.text) < MIN_CHARS_PER_PAGE]
        scanned_total += len(scanned)
        if not scanned or budget <= 0:
            continue
        text_by_page = ocr.ocr_pdf_pages(data, scanned[:budget])
        budget -= len(scanned[:budget])
        local_to_index = {p.page: offset + i for i, p in enumerate(parsed)}
        for local_page, text in text_by_page.items():
            if len(text) < MIN_CHARS_PER_PAGE:
                continue             # read, and still not legible — leave it as it was
            index = local_to_index[local_page]
            pages[index] = SourcePage(pages[index].document, local_page, text)
            recovered_globals.add(index + 1)

    if scanned_total > ocr.MAX_PAGES:
        log.warning(
            "OCR budget exhausted: %d scanned pages in the package, %d read. Raise "
            "OCR_MAX_PAGES if this package matters; every recovered page is a model call.",
            scanned_total, ocr.MAX_PAGES,
        )
    return pages, recovered_globals


def _ocr_quietly(workspace_id: str, tender_id: str,
                 documents: list[tuple[str, bytes]]) -> None:
    """Read the scanned half of the package. A failure here never reaches the uploader.

    WHY IT IS A BACKGROUND PASS. Measured on a real customer corpus
    (docs/ocr-measurement.md): 52% of 478 pages carried no text layer, and the unreadable half
    was almost entirely the bidder's own certificates and licences — the only material an
    answer library can be built from. OCR runs at 3.5s/page on hardware faster than Cloud Run,
    and one real package holds 77 scanned pages: ~157s at best, inside a request the uploader
    is already waiting on. Inline is not an option.

    WHY IT CARRIES THE BYTES. Nothing in this engine persists an uploaded file — there is no
    Storage write anywhere, so there is no later moment at which these pages could be fetched
    again. `BackgroundTasks` runs in-process after the response, so the closure holds them.
    The package is already capped at 50 MB by the request, so this holds no more than the
    request itself did, for as long as the pass runs.

    THE STAMP. Written when the pass finishes, INCLUDING when it recovered nothing — "we read
    the scans and none were legible" is a real answer. Not written when this raised, and not
    written when the deployment has no OCR toolchain: neither is a read that happened.
    """
    # ponytail: no jobs table, same ceiling as _extract_quietly — Cloud Run throttles CPU once
    # the response is flushed, so a queued pass can stall until the next request wakes the
    # instance. min-instances is 1 on the engine, so it is rarely lost outright, and state
    # stays honest either way: ocr_completed_at remains NULL. Add a jobs table if stalled
    # passes start showing up in the logs.
    try:
        if not ocr.available():
            # An ordinary deployment fact, not an error. Every scanned page stays exactly as
            # illegible as the response already said it was.
            log.info("no OCR toolchain here — tender %s keeps its scanned pages unread",
                     tender_id)
            return

        pages, recovered = _ocr_package(documents)
        if recovered:
            _persist_recovered(workspace_id, tender_id, pages, recovered)
        log.info("OCR pass for tender %s recovered %d page(s)", tender_id, len(recovered))
        db.mark_ocr_complete(workspace_id, tender_id, len(recovered))
    except Exception:  # noqa: BLE001 — deliberate: never fail an upload that already returned
        log.exception("background OCR failed for tender %s", tender_id)


def _persist_recovered(workspace_id: str, tender_id: str, pages: list[SourcePage],
                       recovered: set[int]) -> None:
    """Extract from the recovered pages ONLY, and fold the result into the existing tender.

    Extraction is one model call per page, so the pages that already had a text layer are not
    re-read: they were extracted during ingest and re-running them would double both the spend
    and the criteria.
    """
    numbered, page_index = number_package(pages)
    subset = [(p, t) for p, t in numbered if p in recovered]
    result = ingest_pages(subset)

    rows = [_relocate(r, page_index) for r in result["criteria_rows"]]
    if rows:
        db.insert_criteria(workspace_id, tender_id, rows)
    # The G-FR2 denominator. These sentences exist on pages that were invisible at ingest, so
    # without this the backlog would claim the scanned half of the tender says nothing.
    # `insert_unmapped` upserts on (document, page, sentence), so a re-read cannot double them.
    unmapped = [
        {"sentence": r["sentence"],
         "page": page_index[r["page"]].page if r["page"] in page_index else None,
         "document": page_index[r["page"]].document if r["page"] in page_index else None}
        for r in result["unmapped_rows"]
    ]
    if unmapped:
        db.insert_unmapped(workspace_id, tender_id, unmapped)

    # The tender's identity, if page one was the scan. Gated on the placeholder for a reason
    # beyond the rename rule: "Untitled tender" is only produced when the document stated no
    # title, no number AND no authority (display_title), so there is nothing here that this
    # backfill could overwrite with noisier OCR text. A tender that already has a number keeps
    # it. Meta is re-derived from the WHOLE package, not the recovered subset — the document
    # states its identity on page one, wherever that page landed.
    tender = db.get_tender(tender_id, workspace_id) or {}
    if tender.get("title") != PLACEHOLDER_TITLE:
        return
    meta = extract_tender_meta([p.text for p in pages])
    db.set_tender_meta(tender_id, workspace_id, meta.tender_number, meta.authority)
    if renamed := _rename_if_placeholder(workspace_id, tender_id, meta, PLACEHOLDER_TITLE):
        log.info("tender %s named from OCR'd pages: %s", tender_id, renamed)


def _schedule_ocr(background: BackgroundTasks, workspace_id: str, tender_id: str,
                  documents: list[tuple[str, bytes]]) -> None:
    """Queue the scanned-page read for after the response.

    Queued AFTER `_schedule_extraction`, and the order is load-bearing. BackgroundTasks run
    sequentially, and this pass can take minutes; putting it first would park the schedule
    read behind it for no gain. No gain, because OCR-recovered criteria do NOT become schedule
    line items either way: `spec_service.persist_schedule` ran inside the request, and
    `db.replace_line_items` DELETES the tender's schedule before writing, so re-running it
    here would destroy the parameters `_extract_quietly` just paid a model to read. A bidder
    who needs the schedule rebuilt has the deliberate re-read button
    (`POST /api/tenders/{id}/schedule/extract?force=1`); this pass never takes that decision
    for them.
    """
    background.add_task(_ocr_quietly, workspace_id, tender_id, documents)


def _schedule_extraction(background: BackgroundTasks, workspace_id: str,
                         tender_id: str) -> None:
    """Queue the read for after the response.

    NOT inline: `ingest_tender` awaits `_process_ingest` in a threadpool, so the uploader is
    waiting on it, and a real schedule is up to 48 model calls. Extraction is the one part of
    ingest nobody is watching the clock on.
    """
    background.add_task(_extract_quietly, workspace_id, tender_id)


@router.post("/api/tenders/ingest")
async def ingest_tender(
    user: CurrentUser, background: BackgroundTasks,
    file: Annotated[list[UploadFile], File()], title: str = "",
    pursuit_id: str = "",
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
    name = title or documents[0][0] or PLACEHOLDER_TITLE
    # Parsing + extraction + inserts are blocking; keep the event loop free.
    result = await run_in_threadpool(
        _process_ingest, user.workspace_id, documents, name, pursuit_id,
    )
    # Both enrichments run AFTER the response. The upload is the product; these cost model
    # calls and must never delay or fail it. Order is deliberate — see `_schedule_ocr`.
    _schedule_extraction(background, user.workspace_id, result["tender_id"])
    # `illegible_pages` in the response above is the set as it stood BEFORE this ran. It can
    # only shrink afterwards, and the response is already gone — the tender row carries the
    # outcome instead (ocr_completed_at / ocr_pages_recovered, echoed by GET .../readiness).
    _schedule_ocr(background, user.workspace_id, result["tender_id"], documents)
    # Whether those pages will actually be looked at. `ocr.available()` is a deployment fact,
    # not an error — without the toolchain the pass returns quietly and every scanned page
    # stays exactly as unread as this response says (known-pitfalls: the OCR adapter shipped
    # and was called by nothing for a day, and nothing anywhere reported that). The upload
    # screen must not promise a read that cannot happen, and must not tell a user to re-upload
    # a page that is about to be read successfully.
    result["ocr_pending"] = bool(result["illegible_pages"]) and ocr.available()
    return ok(result)


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


@router.patch("/api/tenders/{tender_id}")
def rename_tender(tender_id: str, body: TenderPatch, user: CurrentUser) -> dict:
    """User-given name for a tender the extractor could not title (fallback 'Untitled
    tender'). Mirrors update_project's shape: authz, 404-before-write, no audit — this
    file's neighbouring PATCH doesn't audit renames either."""
    authz.check(user, authz.DRAFT)
    title = body.title.strip()
    if not title:
        raise ApiError(400, "TITLE_REQUIRED", "tender name cannot be empty")
    if not db.get_tender(tender_id, user.workspace_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found in your workspace")
    db.set_tender_title(tender_id, user.workspace_id, title)
    return ok({"id": tender_id, "title": title})


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
