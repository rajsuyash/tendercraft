"""`{ok, data, error}` on every path, including errors. Stack traces are logged, never returned."""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger("tendercraft.evaluate")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def ok(data):
    return {"ok": True, "data": data, "error": None}


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"ok": False, "data": None, "error": {"code": code, "message": message}},
    )


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return _err(exc.status, exc.code, exc.message)


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return _err(422, "VALIDATION_ERROR", "request failed validation")


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled: %s", exc)
    return _err(500, "INTERNAL_ERROR", "an unexpected error occurred")
