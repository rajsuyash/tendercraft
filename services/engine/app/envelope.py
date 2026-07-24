"""The one response shape every endpoint returns (docs/conventions.md, LOCKED §4).

    { "ok": bool, "data": T | null, "error": { "code": str, "message": str } | null }

`code` is a stable string the web UI switches on; stack traces never leave the process.
"""

from __future__ import annotations

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
