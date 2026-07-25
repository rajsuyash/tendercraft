"""The one response shape every endpoint returns (docs/conventions.md, LOCKED §4).

    { "ok": bool, "data": T | null, "error": { "code": str, "message": str } | null }

`code` is a stable string the web UI switches on; stack traces never leave the process.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def ok(data: Any = None) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}


class ApiError(Exception):
    """Raise inside handlers; the global handler renders the envelope."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=err(exc.code, exc.message))


async def validation_error_handler(_: Request, __: Exception) -> JSONResponse:
    """FastAPI's default validation response is {"detail": [...]}, which breaks the LOCKED
    envelope the web UI switches on.

    The message deliberately does NOT echo the validator output: these run on authz-adjacent
    endpoints (e.g. the approval `stage` enum), and enumerating the accepted values is free
    reconnaissance.
    """
    return JSONResponse(status_code=422, content=err("VALIDATION_ERROR", "invalid request"))


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Anything not otherwise handled. Without this, Starlette returns PLAIN TEXT
    'Internal Server Error', which the web route handlers stamp as JSON — so JSON.parse
    throws in the browser and the user gets a blank screen instead of an error state.

    The exception is logged, never serialized: stack traces do not leave the process.
    """
    logging.getLogger("tendercraft.engine").exception("unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content=err("INTERNAL", "internal error"))
