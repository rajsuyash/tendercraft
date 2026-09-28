"""Handing work to Cloud Tasks — the only module that knows a queue exists.

WHY A QUEUE AND NOT BackgroundTasks: Cloud Run throttles CPU once the response is sent, and an
instance reclaimed mid-job takes the work with it and nothing retries it. A task is delivered as
a real HTTP request, so the work runs with full CPU under the engine's own 3600s ceiling, and the
queue redelivers with backoff if the instance dies. Same reasoning as the cron endpoints, which
is also why the receiving endpoint reuses `cron_auth.verify_cron_caller` unchanged: Cloud Tasks
mints the same Google-signed OIDC token Cloud Scheduler does.

Unconfigured is a refusal, never a silent no-op. A queue variable nobody set must fail loudly at
the boundary rather than return an empty result that reads as success — `GEM_CONNECTOR_URL`
taught this the expensive way (docs/known-pitfalls.md).
"""

from __future__ import annotations

import json
import logging
import os

from .envelope import ApiError

log = logging.getLogger("tendercraft.engine")


def _cfg() -> tuple[str, str, str, str]:
    project = os.environ.get("TASKS_PROJECT", "").strip()
    location = os.environ.get("TASKS_LOCATION", "").strip()
    queue = os.environ.get("TASKS_QUEUE", "").strip()
    # The engine's own public URL: the task posts back to us, and it is also the OIDC audience.
    base = (os.environ.get("APP_ENGINE_URL", "").strip()
            or os.environ.get("CRON_AUDIENCE", "").strip())
    if not all((project, location, queue, base)):
        raise ApiError(503, "TASKS_NOT_CONFIGURED",
                       "background jobs are not configured on this deployment "
                       "(TASKS_PROJECT, TASKS_LOCATION, TASKS_QUEUE, CRON_AUDIENCE)")
    return project, location, queue, base


def enqueue_job(job_id: str) -> None:
    """Ask Cloud Tasks to POST /internal/jobs/run back to this service.

    `name` is derived from the job id, so a duplicate enqueue of the same job is refused by the
    queue itself rather than producing two runs.
    """
    from google.cloud import tasks_v2  # imported here: absent in unit tests, present in the image

    project, location, queue, base = _cfg()
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project, location, queue)
    sa = os.environ.get("TASKS_SERVICE_ACCOUNT", "").strip()
    task = {
        "name": f"{parent}/tasks/prepare-{job_id}",
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{base}/internal/jobs/run",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"job_id": job_id}).encode(),
            "oidc_token": {"service_account_email": sa, "audience": base},
        },
    }
    client.create_task(request={"parent": parent, "task": task})
    log.info("jobs: enqueued %s", job_id)
