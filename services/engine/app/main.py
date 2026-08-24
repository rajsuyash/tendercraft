"""TenderCraft engine — FastAPI app factory.

Thin routers over the deterministic engine + AI pipeline. Every response uses the
`{ok,data,error}` envelope; workspace scoping comes from the verified JWT, never the body.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError

from . import db
from .auth import AuthedUser, get_current_user
from .envelope import (
    ApiError,
    api_error_handler,
    ok,
    unhandled_error_handler,
    validation_error_handler,
)

CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


def create_app() -> FastAPI:
    from .analyze_routes import router as analyze_router
    from .cron_routes import router as cron_router
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

    app = FastAPI(title="TenderCraft Engine", version="0.1.0")
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

    @app.get("/health")
    async def health() -> dict:
        # Public liveness check — no auth, no DB dependency (EC-6: deterministic paths
        # stay available even when downstream services are down).
        return ok({"status": "healthy", "service": "tendercraft-engine"})

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
