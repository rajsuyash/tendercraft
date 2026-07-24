"""TenderCraft engine — FastAPI app factory.

Thin routers over the deterministic engine + AI pipeline. Every response uses the
`{ok,data,error}` envelope; tenant scoping comes from the verified JWT, never the body.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI

from .auth import AuthedUser, get_current_user
from .envelope import ApiError, api_error_handler, ok

CurrentUser = Annotated[AuthedUser, Depends(get_current_user)]


def create_app() -> FastAPI:
    from .analyze_routes import router as analyze_router
    from .knowledge_routes import router as knowledge_router
    from .proposal_routes import router as proposal_router
    from .readiness_routes import router as readiness_router
    from .tenders import router as tenders_router

    app = FastAPI(title="TenderCraft Engine", version="0.1.0")
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(tenders_router)
    app.include_router(analyze_router)
    app.include_router(proposal_router)
    app.include_router(readiness_router)
    app.include_router(knowledge_router)

    @app.get("/health")
    async def health() -> dict:
        # Public liveness check — no auth, no DB dependency (EC-6: deterministic paths
        # stay available even when downstream services are down).
        return ok({"status": "healthy", "service": "tendercraft-engine"})

    @app.get("/api/me")
    async def me(user: CurrentUser) -> dict:
        return ok({"user_id": user.user_id, "tenant_id": user.tenant_id, "role": user.role})

    return app


app = create_app()
