"""TenderCraft engine — FastAPI app factory.

Thin routers over the deterministic engine + AI pipeline. Every response uses the
`{ok,data,error}` envelope; workspace scoping comes from the verified JWT, never the body.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool

from . import db, http
from .auth import AuthedUser, get_current_user
from .config import get_settings
from .deterministic import egress
from .envelope import (
    ApiError,
    api_error_handler,
    err,
    ok,
    unhandled_error_handler,
    validation_error_handler,
)

CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


class _JsonFormatter(logging.Formatter):
    """Cloud Logging reads structured stdout: `severity` sets the level, the rest is payload.

    Without this every application log line arrives as `textPayload` at DEFAULT severity, so a
    warning and an info line are indistinguishable in the console and a filter on severity
    returns nothing.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        payload.update(getattr(record, "fields", None) or {})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Set the root level from LOG_LEVEL (default INFO) and install the JSON handler.

    The engine shipped without any logging configuration, which means the root logger sat at
    WARNING and **no `logger.info` line has ever reached Cloud Logging** — seven days of logs
    held zero, confirmed against a positive control. Every INFO the code already writes (the
    egress ledger, the Gemini token/cost line, the cron callers) was being discarded at the
    logger, not lost in transit.

    Handlers already on the root logger are left alone — pytest's `caplog` installs one, and
    clobbering it would make the tests silently stop capturing.
    """
    level = logging.getLevelNamesMapping().get(
        os.environ.get("LOG_LEVEL", "INFO").strip().upper(), logging.INFO
    )
    root = logging.getLogger()
    for existing in [h for h in root.handlers if getattr(h, "_tendercraft", False)]:
        root.removeHandler(existing)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    handler._tendercraft = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)
    # httpx logs one INFO per request carrying the full URL — so turning the root logger on
    # would have doubled every ledger line with a duplicate that spells out the query string
    # (workspace ids, filters) and is billed by the log line. The ledger already reports the
    # method, the table and the bytes, which is the part anyone needs.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _probe_database() -> dict:
    """One row through PostgREST, reporting the status code it got.

    `/health` deliberately touches nothing, which is correct for liveness and useless for the
    failure that actually happened: Supabase answered 402 to every query for two days while
    both services kept returning a cheerful 200. Anything but a 2xx is unhealthy here.

    Uses `db._headers()` rather than `db._rest` on purpose — `_rest` turns every upstream
    status into one ApiError, and the status code IS the diagnosis.
    """
    try:
        headers, url = db._headers(), f"{get_settings().supabase_url}/rest/v1/workspaces"
    except Exception as exc:  # noqa: BLE001 — see below
        # A health check must never BECOME the failure it exists to report. A missing service
        # key raises ApiError and a missing SUPABASE_URL raises RuntimeError (config fails
        # fast, correctly) — both are "the database is unreachable", not a 500.
        return {"healthy": False, "status": None, "detail": str(exc)}
    try:
        r = http.client.request(
            "GET", url, headers=headers, params={"select": "id", "limit": "1"}, timeout=10
        )
    except httpx.HTTPError as exc:
        return {"healthy": False, "status": None, "detail": f"request failed: {exc}"}
    http.note_egress("GET", "workspaces", len(r.content))
    # Accept the CLASS, not a specimen: PostgREST answers 200 or 206 depending on Range.
    healthy = 200 <= r.status_code < 300
    return {
        "healthy": healthy,
        "status": r.status_code,
        "detail": "ok" if healthy else f"supabase returned {r.status_code}",
    }


def create_app() -> FastAPI:
    from .analyze_routes import router as analyze_router
    from .cron_routes import router as cron_router
    from .inbound_routes import router as inbound_router
    from .knowledge_routes import router as knowledge_router
    from .matrix_routes import router as matrix_router
    from .members_routes import router as members_router
    from .opportunities_routes import router as opportunities_router
    from .past_bids_routes import router as past_bids_router
    from .proposal_routes import router as proposal_router
    from .readiness_routes import router as readiness_router
    from .reuse_routes import router as reuse_router
    from .spec_routes import router as spec_router
    from .tenders import router as tenders_router

    configure_logging()
    app = FastAPI(title="TenderCraft Engine", version="0.1.0")

    @app.middleware("http")
    async def attribute_egress(request: Request, call_next):
        """Tag every Supabase byte this request causes with the route that asked for it.

        Set before the handler runs, because that is when the queries happen — a label
        derived after the fact would arrive too late to attribute anything.
        """
        token = http.egress_route.set(
            egress.route_label(request.method, request.url.path)
        )
        try:
            return await call_next(request)
        finally:
            http.egress_route.reset(token)

    app.add_exception_handler(ApiError, api_error_handler)
    # Every error path returns the envelope — including the two that previously did not:
    # request validation (FastAPI's {"detail": ...}) and anything unhandled (plain text).
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(tenders_router)
    app.include_router(analyze_router)
    app.include_router(proposal_router)
    app.include_router(readiness_router)
    app.include_router(knowledge_router)
    app.include_router(members_router)
    app.include_router(matrix_router)
    app.include_router(opportunities_router)
    app.include_router(past_bids_router)
    app.include_router(reuse_router)
    app.include_router(spec_router)
    # Scheduler-facing. Google OIDC, never a Supabase session — see cron_auth.py.
    app.include_router(cron_router)
    # Provider-facing webhook (HMAC) + the actions it raises — see inbound_routes.py.
    app.include_router(inbound_router)

    @app.get("/health")
    async def health() -> dict:
        # Public liveness check — no auth, no DB dependency (EC-6: deterministic paths
        # stay available even when downstream services are down).
        return ok({"status": "healthy", "service": "tendercraft-engine"})

    @app.get("/health/deep")
    async def health_deep(response: Response) -> dict:
        """Liveness that actually reads a row. Cloud Run's readiness stays on `/health`.

        Split deliberately: a container that is up but whose database is blocked must keep
        serving the deterministic screens (EC-6), so this must never gate the revision — it
        exists so a quota block is a failing check rather than an email two days later.
        """
        probe = await run_in_threadpool(_probe_database)
        if not probe["healthy"]:
            response.status_code = 503
            return err("DB_UNHEALTHY", probe["detail"])
        return ok({"status": "healthy", "upstream_status": probe["status"]})

    @app.get("/api/me")
    async def me(user: CurrentUser) -> dict:
        # `market` travels with the identity because the WEB has no tenancy code of its own
        # (known-pitfalls) — the pages that need to know whether they are rendering an Indian or
        # a French workspace must be told, not left to infer it from the reader's language.
        return ok(
            {
                "user_id": user.user_id,
                "workspace_id": user.workspace_id,
                "role": user.role,
                "market": db.get_workspace_market(user.workspace_id),
                # Home market and watched markets are different questions — one governs
                # currency and statutory registers, the other governs the feed (0022).
                "discovery_markets": db.get_workspace_markets(user.workspace_id),
            }
        )

    return app


app = create_app()
