"""Module H endpoints — the manufacturing envelope, the recorded catalogue, and schedule fit.

Answers `docs/feedback/usha-martin.md` asks 2 and 3. Every response uses the standard envelope;
`GET /api/tenders/{id}/schedule` is read-only and never triggers a model call, so a fit screen
still renders during a model outage — reporting `unknown`, which is the truth.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import authz, db, spec_service
from .auth import AuthedUser, get_current_user
from .deterministic.spec_params import PARAM_KEYS, REGISTRY
from .envelope import ApiError, ok

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


class ParameterIn(BaseModel):
    param_key: str
    kind: Literal["numeric", "enum"]
    unit: str | None = Field(default=None, max_length=32)
    num_min: float | None = None
    num_max: float | None = None
    allowed_values: list[str] = Field(default_factory=list, max_length=64)
    raw_text: str = Field(default="", max_length=2000)


class ProductSpecIn(BaseModel):
    spec_kind: Literal["envelope", "catalogue"]
    label: str = Field(min_length=1, max_length=200)
    standard_ref: str | None = Field(default=None, max_length=100)
    parent_envelope_id: str | None = None
    gem_catalogue_id: str | None = Field(default=None, max_length=100)
    parameters: list[ParameterIn] = Field(default_factory=list, max_length=64)


def _validated(parameters: list[ParameterIn]) -> list[dict]:
    """Reject a parameter that cannot decide anything, before it reaches the database.

    The CHECK constraints would refuse these too, but a 400 naming the parameter is a usable
    error and a Postgres constraint violation surfacing through PostgREST is not.
    """
    rows = []
    for p in parameters:
        if p.param_key not in REGISTRY:
            raise ApiError(400, "SPEC_PARAM_UNKNOWN",
                           f"'{p.param_key}' is not a known parameter")
        if p.kind == "numeric" and p.num_min is None and p.num_max is None:
            raise ApiError(400, "SPEC_PARAM_UNBOUNDED",
                           f"'{p.param_key}' needs at least a minimum or a maximum")
        if (p.num_min is not None and p.num_max is not None and p.num_min > p.num_max):
            raise ApiError(400, "SPEC_PARAM_RANGE",
                           f"'{p.param_key}' has a minimum above its maximum")
        values = [v.strip() for v in p.allowed_values if v.strip()]
        if p.kind == "enum" and not values:
            raise ApiError(400, "SPEC_PARAM_NO_VALUES",
                           f"'{p.param_key}' needs at least one value")
        rows.append({
            "param_key": p.param_key, "kind": p.kind, "unit": p.unit,
            "num_min": p.num_min, "num_max": p.num_max, "allowed_values": values,
            "raw_text": p.raw_text, "confirmed": True,
        })
    return rows


@router.get("/api/spec-parameters")
def list_parameter_registry(user: CurrentUser) -> dict:
    """The allowlist, for the envelope editor's dropdown. A UI array mirroring a server enum
    WILL drift (docs/known-pitfalls.md) — so the UI reads it from here rather than repeating it."""
    return ok({
        "parameters": [
            {"key": k, "label": REGISTRY[k].label, "kind": REGISTRY[k].kind.value,
             "canonical_unit": REGISTRY[k].canonical_unit}
            for k in PARAM_KEYS
        ]
    })


@router.get("/api/product-specs")
def list_product_specs(user: CurrentUser) -> dict:
    return ok({"specs": db.get_capability_specs(user.workspace_id)})


@router.post("/api/product-specs")
def save_product_spec(body: ProductSpecIn, user: CurrentUser) -> dict:
    authz.check(user, authz.DRAFT)
    rows = _validated(body.parameters)
    if body.spec_kind == "envelope" and body.parent_envelope_id:
        raise ApiError(400, "SPEC_PARENT_INVALID",
                       "only a catalogue item records the envelope it came from")
    if body.parent_envelope_id and not db.get_product_spec(body.parent_envelope_id,
                                                          user.workspace_id):
        # Ownership guard before binding a caller-supplied id — one query covers ET-6
        # (docs/known-pitfalls.md: binding a foreign id is a cross-workspace write).
        raise ApiError(404, "SPEC_NOT_FOUND", "parent envelope not found")

    spec = db.upsert_product_spec(user.workspace_id, {
        "spec_kind": body.spec_kind, "label": body.label,
        "standard_ref": body.standard_ref, "parent_envelope_id": body.parent_envelope_id,
        "gem_catalogue_id": body.gem_catalogue_id, "created_by": user.user_id,
    })
    if not spec:
        raise ApiError(500, "SPEC_SAVE_FAILED", "could not save the specification")
    db.replace_spec_parameters(user.workspace_id, product_spec_id=spec["id"], rows=rows)
    return ok({"spec_id": spec["id"], "parameters": len(rows)})


@router.delete("/api/product-specs/{spec_id}")
def remove_product_spec(spec_id: str, user: CurrentUser) -> dict:
    authz.check(user, authz.DRAFT)
    if not db.get_product_spec(spec_id, user.workspace_id):
        raise ApiError(404, "SPEC_NOT_FOUND", "specification not found")
    db.delete_product_spec(spec_id, user.workspace_id)
    return ok({"deleted": spec_id})


@router.get("/api/tenders/{tender_id}/schedule")
def get_schedule(tender_id: str, user: CurrentUser) -> dict:
    """Read-only fit. No model call, so this renders during an outage — as `unknown`."""
    if not db.get_tender(tender_id, user.workspace_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found")
    return ok(spec_service.assess_schedule(user.workspace_id, tender_id))


@router.post("/api/tenders/{tender_id}/schedule/extract")
async def extract_schedule(tender_id: str, user: CurrentUser) -> dict:
    """Read the specifications out of the schedule's descriptions. The only model call here.

    Separate from the GET on purpose: extraction costs money and the fit screen is looked at
    far more often than a schedule changes.
    """
    authz.check(user, authz.DRAFT)
    if not db.get_tender(tender_id, user.workspace_id):
        raise ApiError(404, "TENDER_NOT_FOUND", "tender not found")

    def _run() -> dict:
        items = db.get_line_items(tender_id, user.workspace_id)
        if not items:
            raise ApiError(409, "SCHEDULE_EMPTY",
                           "no schedule lines on this tender — upload a BOQ or add items")
        populated = spec_service.extract_schedule(user.workspace_id, items)
        return {"lines": len(items), "populated": populated,
                **spec_service.assess_schedule(user.workspace_id, tender_id)}

    return ok(await run_in_threadpool(_run))
