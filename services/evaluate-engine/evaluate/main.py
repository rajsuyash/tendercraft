"""TenderCraft Evaluate — FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from .envelope import (
    ApiError,
    api_error_handler,
    ok,
    unhandled_error_handler,
    validation_error_handler,
)


def create_app() -> FastAPI:
    from .routes import router

    app = FastAPI(title="TenderCraft Evaluate Engine", version="0.1.0")
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict:
        return ok({"status": "healthy", "service": "tendercraft-evaluate-engine"})

    return app


app = create_app()
