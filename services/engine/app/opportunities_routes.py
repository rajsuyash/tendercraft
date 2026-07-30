"""Opportunity feed endpoints (Module F, screens S14/S16).

Workspace scoping comes from the verified JWT, never the body — the shared corpus is public but
every decision about it is not. The Excluded bucket is a first-class response field rather than
a separate endpoint, because F-FR12 requires its count to be visible from the primary feed at
all times: a filter you cannot see is indistinguishable from a bug that ate your tenders.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import db
from .auth import AuthedUser, get_current_user
from .deterministic.discovery import RULE_KINDS
from .discovery import ingest
from .envelope import ApiError, ok

router = APIRouter()
CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str
    spec: dict = Field(default_factory=dict)
    enabled: bool = True


class MatchPatch(BaseModel):
    watched: bool | None = None
    assigned_to: str | None = None


@router.get("/api/opportunities")
async def list_opportunities(
    user: CurrentUser,
    state: Literal["in_scope", "excluded"] = "in_scope",
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """The feed. Always returns BOTH counts, whichever bucket was asked for."""

    def work() -> dict:
        rows = db.get_feed(user.workspace_id, state, limit=limit)
        return {
            "state": state,
            "items": rows,
            "counts": {
                "in_scope": db.count_feed(user.workspace_id, "in_scope"),
                "excluded": db.count_feed(user.workspace_id, "excluded"),
                "likely_eligible": db.count_eligible(user.workspace_id),
            },
            "rules": db.get_discovery_rules(user.workspace_id),
        }

    return ok(await run_in_threadpool(work))


@router.post("/api/opportunities/refresh")
async def refresh(user: CurrentUser, max_pages: int = Query(default=8, ge=1, le=60)) -> dict:
    """Sweep the connector, then re-run this workspace's gate.

    Sync work in a threadpool: the sweep sleeps between portal requests to honour the rate cap,
    and sleeping on the event loop would stall every other request in the container
    (docs/known-pitfalls.md).
    """

    def work() -> dict:
        swept = ingest.refresh_corpus(max_pages=max_pages)
        matched = ingest.recompute_matches(user.workspace_id)
        return {"swept": swept, "matched": matched}

    try:
        return ok(await run_in_threadpool(work))
    except RuntimeError as exc:
        raise ApiError(503, "CONNECTOR_UNAVAILABLE", str(exc)) from exc


@router.post("/api/opportunities/rules")
async def create_rule(body: RuleIn, user: CurrentUser) -> dict:
    if body.kind not in RULE_KINDS:
        # Named explicitly rather than echoed from a validator: the closed set is mirrored in
        # the UI, and a drifted option should say which side drifted.
        raise ApiError(422, "UNKNOWN_RULE_KIND", f"rule kind '{body.kind}' is not supported")

    def work() -> dict:
        rule = db.create_discovery_rule(user.workspace_id, body.model_dump())
        # A new rule changes what the user can see, so the feed is recomputed before returning —
        # otherwise the rule appears to have done nothing until the next sweep.
        recomputed = ingest.recompute_matches(user.workspace_id, doc_budget=0)
        return {"rule": rule, "recomputed": recomputed}

    return ok(await run_in_threadpool(work))


@router.delete("/api/opportunities/rules/{rule_id}")
async def delete_rule(rule_id: str, user: CurrentUser) -> dict:
    def work() -> dict:
        db.delete_discovery_rule(rule_id, user.workspace_id)
        # Deleting a rule must return the hidden tenders immediately. Nothing stays excluded by
        # a rule that no longer exists — that would be an exclusion with no author (F-AC6).
        return ingest.recompute_matches(user.workspace_id, doc_budget=0)

    return ok(await run_in_threadpool(work))


@router.patch("/api/opportunities/{opportunity_id}")
async def patch_match(opportunity_id: str, body: MatchPatch, user: CurrentUser) -> dict:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise ApiError(422, "EMPTY_PATCH", "no fields to update")

    def work() -> list[dict]:
        rows = db.set_match_flags(user.workspace_id, opportunity_id, patch)
        if not rows:
            # The row belongs to another workspace or does not exist. 404 either way: a
            # distinguishable 403 would confirm the opportunity exists in someone else's feed.
            raise ApiError(404, "NOT_FOUND", "opportunity not in this workspace's feed")
        return rows

    return ok(await run_in_threadpool(work))
