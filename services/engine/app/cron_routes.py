"""The scheduled entry points: the two jobs UML's asks 1 and 4 need in order to be automatic.

`dispatch_digest` and `check_watched_stages` were written for a scheduler — idempotent, gated
on a per-workspace opt-in, returning a report rather than raising on "nothing to do". What was
missing was a caller with no user behind it. This module is only that: authenticate the
scheduler (`cron_auth`), work out which workspaces opted in (`db`), and call the existing
service function once per workspace.

**No new decisions live here.** Whether a tender is worth an email is `deterministic/notify.py`;
whether a stage move is worth announcing is `deterministic/stage_watch.py`. A scheduled run and
a button press must produce the same outcome, so they call the same function — the moment this
route grows its own threshold, the two paths start disagreeing and only one of them is tested.

Mounted under `/internal/` rather than `/api/` because the audience is different: `/api/*` is
the browser's, and everything there answers to a Supabase session. Nothing under `/internal/`
will ever be reachable with one.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header
from starlette.concurrency import run_in_threadpool

from . import db, notify_service
from .cron_auth import verify_cron_caller
from .envelope import ApiError, ok

log = logging.getLogger(__name__)

router = APIRouter()

#: Per-workspace cap for one scheduled stage sweep. Each watched bid costs up to three requests
#: to a government portal, so this is a politeness budget as much as a performance one.
_WATCH_LIMIT = 25


def _sweep(workspace_ids: list[str], run: object, job: str) -> dict:
    """Run `run(workspace_id)` across workspaces, surviving a per-workspace failure.

    One workspace's misconfiguration — alerts enabled with no mail transport, a portal timing
    out — must never cost every other workspace its run. The failure is reported per workspace
    rather than raised, because a scheduler sees only a status code and a 500 here would say
    "nothing ran" when almost everything did.
    """
    results, failures = [], []
    for workspace_id in workspace_ids:
        try:
            results.append({"workspace_id": workspace_id, "result": run(workspace_id)})
        except Exception as exc:  # noqa: BLE001 — see docstring
            log.exception("%s failed for workspace %s", job, workspace_id)
            failures.append({"workspace_id": workspace_id, "error": str(exc)})
    return {"job": job, "workspaces": len(workspace_ids),
            "ran": len(results), "failed": len(failures),
            "results": results, "failures": failures}


@router.post("/internal/cron/digest")
async def cron_digest(authorization: str | None = Header(default=None)) -> dict:
    """Email every opted-in workspace the relevant tenders nobody has been told about yet.

    UML ask 1's *"automatically… circulated to the respective Zonal Heads"*. Safe to run often:
    `select_for_digest` is given the already-sent ledger, so a second run in the same hour sends
    nothing rather than sending twice.
    """
    caller = verify_cron_caller(authorization)
    log.info("cron digest requested by %s", caller)

    def work() -> dict:
        return _sweep(db.list_notifying_workspaces(), notify_service.dispatch_digest, "digest")

    return ok(await run_in_threadpool(work))


@router.post("/internal/cron/watch")
async def cron_watch(authorization: str | None = Header(default=None)) -> dict:
    """Poll every watched bid's evaluation stage and announce the forward moves.

    UML ask 4's *"monitor the tender status… as soon as they are generated"* — as far as a
    public page can answer it. This reports the STAGE; the clarification itself is behind the
    GeM seller login and is not ours to read (G-1/G-8).
    """
    caller = verify_cron_caller(authorization)
    log.info("cron watch requested by %s", caller)

    def work() -> dict:
        return _sweep(
            db.list_watching_workspaces(),
            lambda ws: notify_service.check_watched_stages(ws, _WATCH_LIMIT),
            "watch",
        )

    return ok(await run_in_threadpool(work))


@router.get("/internal/cron/health")
async def cron_health(authorization: str | None = Header(default=None)) -> dict:
    """Prove the scheduler's identity reaches this service, without doing any work.

    Exists so a misconfigured `CRON_AUDIENCE` is a one-request diagnosis instead of being
    discovered as an unexplained absence of emails a week later.
    """
    try:
        caller = verify_cron_caller(authorization)
    except ApiError:
        raise
    return ok({"caller": caller,
               "notifying_workspaces": len(await run_in_threadpool(db.list_notifying_workspaces)),
               "watching_workspaces": len(await run_in_threadpool(db.list_watching_workspaces))})
