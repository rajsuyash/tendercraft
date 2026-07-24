"""Engine data access via Supabase PostgREST (service role).

The engine uses the service key, which BYPASSES RLS — so every function here MUST scope
by tenant_id explicitly (the code enforces what RLS would). A missing tenant filter is an
ET-6 defect (known-pitfalls: service-role bypasses RLS).
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import get_settings
from .envelope import ApiError


def _headers() -> dict[str, str]:
    key = get_settings().supabase_service_key
    if not key:
        raise ApiError(500, "ENGINE_MISCONFIGURED", "service key not configured")
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _rest(method: str, path: str, *, params: dict | None = None, json: Any = None) -> Any:
    s = get_settings()
    try:
        r = httpx.request(
            method,
            f"{s.supabase_url}/rest/v1/{path}",
            headers={**_headers(), "Prefer": "return=representation"},
            params=params,
            json=json,
            timeout=15,
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise ApiError(502, "DB_ERROR", f"database request failed: {exc}") from exc
    return r.json() if r.text else None


def create_tender(tenant_id: str, title: str) -> dict:
    rows = _rest("POST", "tenders", json={"tenant_id": tenant_id, "title": title})
    return rows[0]


def get_tender(tender_id: str, tenant_id: str) -> dict | None:
    rows = _rest(
        "GET", "tenders",
        params={"id": f"eq.{tender_id}", "tenant_id": f"eq.{tenant_id}", "select": "*"},
    )
    return rows[0] if rows else None


def insert_criteria(tenant_id: str, tender_id: str, criteria: list[dict]) -> list[dict]:
    payload = [{**c, "tenant_id": tenant_id, "tender_id": tender_id} for c in criteria]
    return _rest("POST", "criteria", json=payload) or []


def get_criteria(tender_id: str, tenant_id: str) -> list[dict]:
    return (
        _rest(
            "GET", "criteria",
            params={"tender_id": f"eq.{tender_id}", "tenant_id": f"eq.{tenant_id}", "select": "*"},
        )
        or []
    )


def confirm_criterion(criterion_id: str, tenant_id: str) -> list[dict]:
    return _rest(
        "PATCH", "criteria",
        params={"id": f"eq.{criterion_id}", "tenant_id": f"eq.{tenant_id}"},
        json={"confirmed": True},
    )


def set_tender_locked(tender_id: str, tenant_id: str, locked_at: str) -> None:
    _rest(
        "PATCH", "tenders",
        params={"id": f"eq.{tender_id}", "tenant_id": f"eq.{tenant_id}"},
        json={"status": "locked", "locked_at": locked_at},
    )
