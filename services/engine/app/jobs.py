"""Job lifecycle — the state a long unit of work leaves behind so a lost client can find it.

Pure state transitions over `db`. No HTTP, no queue, no model imports: enqueueing lives in
`app/tasks.py` and the work itself in the route. That split is what lets every transition here
be unit-tested without a network.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from . import db
from .envelope import ApiError

log = logging.getLogger("tendercraft.engine")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def start(workspace_id: str, tender_id: str, kind: str) -> dict[str, Any]:
    """Create a queued job, or return the one already in flight.

    Returning the existing row rather than raising is deliberate: a second click is a user
    asking "is it working?", and the honest answer is the running job, not an error.
    """
    active = db.get_active_job_for_tender(workspace_id, tender_id, kind)
    if active:
        log.info("jobs: %s already active for tender %s", kind, tender_id)
        return active
    return db.create_job(workspace_id, tender_id, kind)


def claim(job_id: str) -> dict[str, Any]:
    row = db.get_job(job_id) or {}
    return db.update_job(job_id, {
        "state": "running",
        "started_at": row.get("started_at") or _now(),
        "attempts": int(row.get("attempts") or 0) + 1,
    })


def should_run(job_id: str, stage: str) -> bool:
    """False when a redelivery is re-covering ground already paid for."""
    row = db.get_job(job_id) or {}
    return stage not in (row.get("done_stages") or [])


def begin_stage(job_id: str, stage: str) -> None:
    db.update_job(job_id, {"stage": stage})


def finish_stage(job_id: str, stage: str) -> None:
    row = db.get_job(job_id) or {}
    done = list(row.get("done_stages") or [])
    if stage not in done:
        done.append(stage)
    db.update_job(job_id, {"done_stages": done})


def succeed(job_id: str) -> None:
    db.update_job(job_id, {"state": "succeeded", "stage": None, "finished_at": _now()})


def fail(job_id: str, exc: BaseException) -> None:
    """Record why, in the taxonomy the UI already switches on.

    An ApiError carries a stable code; anything else is ours and gets JOB_FAILED. The message
    is the exception's own text and never a traceback — traces go to the log (conventions.md).
    """
    if isinstance(exc, ApiError):
        code, message = exc.code, exc.message
    else:
        code, message = "JOB_FAILED", str(exc) or exc.__class__.__name__
        log.exception("jobs: %s failed", job_id)
    db.update_job(job_id, {
        "state": "failed", "error_code": code, "error_message": message[:500],
        "finished_at": _now(),
    })
