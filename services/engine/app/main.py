"""TenderCraft engine — FastAPI app factory.

Thin routers over the deterministic engine + AI pipeline. Every response uses the
`{ok,data,error}` envelope; workspace scoping comes from the verified JWT, never the body.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError

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
    from .knowledge_routes import router as knowledge_router
    from .members_routes import router as members_router
    from .proposal_routes import router as proposal_router
    from .readiness_routes import router as readiness_router
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

    @app.get("/health")
    async def health() -> dict:
        # Public liveness check — no auth, no DB dependency (EC-6: deterministic paths
        # stay available even when downstream services are down).
        return ok({"status": "healthy", "service": "tendercraft-engine"})

    @app.get("/api/me")
    async def me(user: CurrentUser) -> dict:
        return ok({"user_id": user.user_id, "workspace_id": user.workspace_id, "role": user.role})

    return app


app = create_app()
