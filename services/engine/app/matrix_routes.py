"""Compliance-matrix endpoints (Module G).

The matrix exists from TOM lock onward, with no proposal and no Generator run — that is the
whole point. A bid manager who will draft in Word still gets the artifact they would otherwise
have spent a day building in Excel, plus a denominator proving nothing was dropped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import db, matrix_export
from .auth import AuthedUser, get_current_user
from .deterministic.matrix import (
    CriterionSpec,
    MatrixRow,
    MatrixRowStatus,
    UnmappedResolution,
    coverage_of_rows,
    evaluate_matrix_complete,
    generate_rows,
    plan_import,
)
from .deterministic.types import RequirementLevel, SourceAnchor
from .envelope import ApiError, ok

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]

#: The sheet displays Owner but may not write it back — see plan_import's docstring.
_IMPORT_IGNORED = ("owner",)


class RowPatch(BaseModel):
    response_ref: str | None = Field(default=None, max_length=200)
    owner: str | None = None
    status: MatrixRowStatus | None = None
    due_date: str | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ResolveIn(BaseModel):
    # 'open' is absent deliberately: resolving is a forward action, and re-opening a
    # dismissed sentence is a different (unbuilt) decision that would need its own audit line.
    resolution: Literal["not_a_requirement", "mapped"]


def _anchor(row: dict) -> SourceAnchor | None:
    page, clause = row.get("anchor_page"), row.get("anchor_clause")
    if not page:
        return None
    return SourceAnchor(page=page, clause=clause or "", document=row.get("anchor_document") or "")


def _to_row(row: dict) -> MatrixRow:
    return MatrixRow(
        criterion_id=row["criterion_id"],
        requirement_text=row["requirement_text"],
        requirement_level=RequirementLevel(row["requirement_level"]),
        anchor=_anchor(row),
        evidence_required=row.get("evidence_required"),
        response_ref=row.get("response_ref"),
        owner=row.get("owner"),
        status=MatrixRowStatus(row["status"]),
        due_date=row.get("due_date"),
        notes=row.get("notes"),
    )


def _row_payload(row: dict) -> dict:
    return {
        "id": row["id"],
        "criterion_id": row["criterion_id"],
        "requirement_text": row["requirement_text"],
        "requirement_level": row["requirement_level"],
        "anchor_page": row.get("anchor_page"),
        "anchor_clause": row.get("anchor_clause"),
        "anchor_document": row.get("anchor_document"),
        "evidence_required": row.get("evidence_required"),
        "response_ref": row.get("response_ref"),
        "owner": row.get("owner"),
        "status": row["status"],
        "due_date": row.get("due_date"),
        "notes": row.get("notes"),
    }


def _require_tender(tender_id: str, user: AuthedUser) -> dict:
    """Prove the tender belongs to this workspace BEFORE any service-role write.

    The engine writes with the service key, which bypasses RLS, so a caller-supplied id must
    be checked in code — this is the cross-workspace write class this codebase has been bitten
    by before.
    """
    tender = db.get_tender(tender_id, user.workspace_id)
    if not tender:
        raise ApiError(404, "NOT_FOUND", "tender not found")
    return tender


def _load(tender_id: str, user: AuthedUser) -> dict:
    tender = _require_tender(tender_id, user)
    stored = db.get_matrix_rows(tender_id, user.workspace_id)
    unmapped = db.get_unmapped(tender_id, user.workspace_id)
    rows = [_to_row(r) for r in stored]
    open_unmapped = [u for u in unmapped if u["resolution"] == UnmappedResolution.OPEN.value]
    cov = coverage_of_rows(rows)
    gate = evaluate_matrix_complete(rows, len(open_unmapped))

    return {
        "tender": tender,
        "stored": stored,
        "rows": rows,
        "payload": {
            "tender_id": tender_id,
            "title": tender.get("title"),
            "locked_at": tender.get("locked_at"),
            "rows": [_row_payload(r) for r in stored],
            # ONE coverage figure, from app/deterministic/matrix.coverage (G-FR7). Every
            # surface reads this — never its own arithmetic.
            "coverage": {
                "total": cov.total,
                "resolved": cov.resolved,
                "mandatory_total": cov.mandatory_total,
                "mandatory_resolved": cov.mandatory_resolved,
                "fraction": cov.fraction,
                "mandatory_fraction": cov.mandatory_fraction,
            },
            "unmapped": [
                {
                    "id": u["id"],
                    "sentence": u["sentence"],
                    "page": u.get("page"),
                    "resolution": u["resolution"],
                }
                for u in unmapped
            ],
            "open_unmapped": len(open_unmapped),
            "complete": gate.ok,
            "blockers": list(gate.blockers),
        },
    }


@router.post("/api/tenders/{tender_id}/matrix")
def generate(tender_id: str, user: CurrentUser) -> dict:
    """Generate (or refresh) the matrix from the locked TOM.

    Refresh is a merge, not a rebuild: re-running after a corrigendum updates requirement text
    while owners and statuses survive. Losing a week of assignment state to a re-generate would
    be a reason never to press the button.
    """
    tender = _require_tender(tender_id, user)
    if not tender.get("locked_at"):
        raise ApiError(
            409,
            "TOM_NOT_LOCKED",
            "lock the tender model before generating a matrix — the matrix copies requirement "
            "text from it, and an unlocked model can still change",
        )

    criteria = db.get_criteria(tender_id, user.workspace_id)
    if not criteria:
        raise ApiError(409, "NO_CRITERIA", "this tender has no criteria to build a matrix from")

    specs = [
        CriterionSpec(
            id=c["id"],
            verbatim_text=c["verbatim_text"],
            requirement_level=RequirementLevel(c["requirement_level"]),
            anchor=_anchor(c),
            evidence_required=c.get("evidence_required"),
        )
        for c in criteria
    ]
    rows = generate_rows(specs)
    db.upsert_matrix_rows(
        user.workspace_id,
        tender_id,
        [
            {
                "criterion_id": r.criterion_id,
                "requirement_text": r.requirement_text,
                "requirement_level": r.requirement_level.value,
                "anchor_page": r.anchor.page if r.anchor else None,
                "anchor_clause": r.anchor.clause if r.anchor else None,
                "anchor_document": (r.anchor.document or None) if r.anchor else None,
                "evidence_required": r.evidence_required,
            }
            for r in rows
        ],
    )
    return ok(_load(tender_id, user)["payload"])


@router.get("/api/tenders/{tender_id}/matrix")
def get_matrix(tender_id: str, user: CurrentUser) -> dict:
    return ok(_load(tender_id, user)["payload"])


@router.patch("/api/tenders/{tender_id}/matrix/rows/{row_id}")
def patch_row(tender_id: str, row_id: str, patch: RowPatch, user: CurrentUser) -> dict:
    _require_tender(tender_id, user)
    fields = patch.model_dump(exclude_unset=True)
    if not fields:
        raise ApiError(400, "NO_FIELDS", "no editable fields supplied")
    if "status" in fields and fields["status"] is not None:
        fields["status"] = fields["status"].value
    fields["updated_at"] = datetime.now(UTC).isoformat()

    updated = db.update_matrix_row(row_id, tender_id, user.workspace_id, fields)
    if not updated:
        raise ApiError(404, "NOT_FOUND", "matrix row not found in this tender")
    return ok(_load(tender_id, user)["payload"])


@router.post("/api/tenders/{tender_id}/matrix/unmapped/{unmapped_id}/resolve")
def resolve_unmapped(
    tender_id: str, unmapped_id: str, body: ResolveIn, user: CurrentUser
) -> dict:
    """Dismiss or map one requirement sentence.

    Dismissal is a human claim that a sentence is not a requirement. It is recorded with the
    actor and timestamp — the denominator's credibility rests on the dismissals being
    attributable, not on the count being small.
    """
    _require_tender(tender_id, user)
    updated = db.resolve_unmapped(
        unmapped_id,
        user.workspace_id,
        body.resolution,
        user.user_id,
        datetime.now(UTC).isoformat(),
    )
    if not updated:
        raise ApiError(404, "NOT_FOUND", "unmapped sentence not found")
    return ok(_load(tender_id, user)["payload"])


@router.get("/api/tenders/{tender_id}/matrix/export.xlsx")
async def export_xlsx(tender_id: str, user: CurrentUser) -> Response:
    """Download the matrix as .xlsx.

    Returns bytes on 2xx — the same documented deviation from the envelope as the DOCX export
    (docs/conventions.md). Every error path still returns the envelope.
    """
    loaded = await run_in_threadpool(_load, tender_id, user)
    if not loaded["rows"]:
        raise ApiError(409, "NO_MATRIX", "generate the matrix first")

    title = loaded["tender"].get("title") or "tender"
    data = await run_in_threadpool(matrix_export.build_xlsx, loaded["rows"], title)
    safe = "".join(c for c in title if c.isalnum() or c in " -_")[:60].strip() or "matrix"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe} - compliance matrix.xlsx"'},
    )


@router.post("/api/tenders/{tender_id}/matrix/import")
async def import_xlsx(
    tender_id: str, user: CurrentUser, file: Annotated[UploadFile, File()]
) -> dict:
    """Re-import an edited sheet.

    Never a last-write-wins merge. Conflicts are returned with the whole plan withheld: a
    partial apply would leave the user unable to say which of their edits landed, on the one
    artifact whose job is to be exhaustive.
    """
    _require_tender(tender_id, user)
    data = await file.read()
    incoming, parse_conflicts = await run_in_threadpool(matrix_export.parse_xlsx, data)

    loaded = await run_in_threadpool(_load, tender_id, user)
    plan = plan_import(loaded["rows"], incoming, ignore_fields=_IMPORT_IGNORED)
    conflicts = parse_conflicts + plan.conflicts

    if conflicts:
        raise ApiError(
            409,
            "MATRIX_IMPORT_CONFLICT",
            "; ".join(
                f"{c.criterion_id} · {c.field}: {c.reason}" for c in conflicts[:10]
            )
            + (f" (+{len(conflicts) - 10} more)" if len(conflicts) > 10 else ""),
        )

    by_criterion = {r["criterion_id"]: r["id"] for r in loaded["stored"]}
    now = datetime.now(UTC).isoformat()
    for row in plan.updates:
        db.update_matrix_row(
            by_criterion[row.criterion_id],
            tender_id,
            user.workspace_id,
            {
                "response_ref": row.response_ref,
                "status": row.status.value,
                "due_date": row.due_date,
                "notes": row.notes,
                "updated_at": now,
            },
        )

    payload = (await run_in_threadpool(_load, tender_id, user))["payload"]
    return ok(
        {
            **payload,
            "imported": len(plan.updates),
            "unchanged": plan.unchanged,
            "ignored_fields": list(_IMPORT_IGNORED),
        }
    )
