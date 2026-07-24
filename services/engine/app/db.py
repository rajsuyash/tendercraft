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


def _rest(
    method: str, path: str, *, params: dict | None = None, json: Any = None,
    prefer: str = "return=representation",
) -> Any:
    s = get_settings()
    try:
        r = httpx.request(
            method,
            f"{s.supabase_url}/rest/v1/{path}",
            headers={**_headers(), "Prefer": prefer},
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


# ---------- vendor profile (Module C) ----------
def get_profile_context(tenant_id: str) -> dict:
    """Assemble the full structured profile for eligibility evaluation."""
    scope = {"tenant_id": f"eq.{tenant_id}"}

    def sel(table: str, cols: str) -> list:
        return _rest("GET", table, params={**scope, "select": cols}) or []

    legal = sel("vendor_profiles", "*")
    return {
        "legal_identity": legal[0] if legal else {},
        "financials": sel("profile_financials", "fy_label,turnover_cr"),
        "experience_records": sel(
            "experience_records", "id,project_name,client_type,value_cr,scope_tags,completion_date"
        ),
        "certifications": sel("certifications", "id,name,cert_no,valid_from,valid_to"),
    }


# ---------- analyses ----------
def save_analysis(tenant_id: str, tender_id: str, result: dict) -> None:
    _rest(
        "POST", "analyses",
        params={"on_conflict": "tender_id"},
        json={"tenant_id": tenant_id, "tender_id": tender_id, "result": result},
        prefer="resolution=merge-duplicates",
    )


def get_analysis(tender_id: str, tenant_id: str) -> dict | None:
    rows = _rest(
        "GET", "analyses",
        params={"tender_id": f"eq.{tender_id}", "tenant_id": f"eq.{tenant_id}", "select": "result"},
    )
    return rows[0]["result"] if rows else None


# ---------- content library + proposals (Module B) ----------
def insert_library_document(tenant_id: str, doc: dict, uploaded_by: str | None) -> dict:
    rows = _rest(
        "POST", "library_documents",
        json={**doc, "tenant_id": tenant_id, "uploaded_by": uploaded_by},
    )
    return rows[0]


def get_valid_library_docs(tenant_id: str, today_iso: str) -> list[dict]:
    """Retrieval with the validity HARD-filter: expired docs are excluded (never a model choice)."""
    docs = _rest(
        "GET", "library_documents",
        params={"tenant_id": f"eq.{tenant_id}", "select": "id,name,doc_type,text_content,valid_to"},
    ) or []
    return [d for d in docs if not d.get("valid_to") or d["valid_to"] >= today_iso]


def create_proposal(tenant_id: str, tender_id: str) -> dict:
    rows = _rest(
        "POST", "proposals",
        params={"on_conflict": "tender_id"},
        json={"tenant_id": tenant_id, "tender_id": tender_id, "status": "draft"},
        prefer="resolution=merge-duplicates,return=representation",
    )
    return rows[0]


def upsert_response(tenant_id: str, proposal_id: str, criterion_id: str, resp: dict) -> None:
    _rest(
        "POST", "proposal_responses",
        params={"on_conflict": "proposal_id,criterion_id"},
        json={
            "tenant_id": tenant_id,
            "proposal_id": proposal_id,
            "criterion_id": criterion_id,
            **resp,
        },
        prefer="resolution=merge-duplicates",
    )


def get_proposal_by_tender(tender_id: str, tenant_id: str) -> dict | None:
    rows = _rest(
        "GET", "proposals",
        params={"tender_id": f"eq.{tender_id}", "tenant_id": f"eq.{tenant_id}", "select": "*"},
    )
    return rows[0] if rows else None


def get_responses(proposal_id: str, tenant_id: str) -> list[dict]:
    return _rest(
        "GET", "proposal_responses",
        params={"proposal_id": f"eq.{proposal_id}", "tenant_id": f"eq.{tenant_id}", "select": "*"},
    ) or []


# ---------- approvals + audit + export (Module E) ----------
def get_approvals(proposal_id: str, tenant_id: str) -> list[dict]:
    return _rest(
        "GET", "proposal_approvals",
        params={"proposal_id": f"eq.{proposal_id}", "tenant_id": f"eq.{tenant_id}", "select": "*"},
    ) or []


def add_approval(tenant_id: str, proposal_id: str, stage: str, approver: str) -> None:
    _rest(
        "POST", "proposal_approvals",
        params={"on_conflict": "proposal_id,stage"},
        json={
            "tenant_id": tenant_id, "proposal_id": proposal_id,
            "stage": stage, "approver": approver,
        },
        prefer="resolution=merge-duplicates",
    )


def mark_exported(proposal_id: str, tenant_id: str, when_iso: str) -> None:
    _rest(
        "PATCH", "proposals",
        params={"id": f"eq.{proposal_id}", "tenant_id": f"eq.{tenant_id}"},
        json={"status": "exported", "exported_at": when_iso},
    )


def write_audit(tenant_id: str, actor: str | None, action: str, entity: str, entity_id: str | None,
                before: dict | None = None, after: dict | None = None) -> None:
    """Append an immutable audit event (E-FR4). Never fails the caller — audit is best-effort
    at the app layer, but the DB triggers guarantee it can't be altered once written."""
    try:
        _rest(
            "POST", "audit_events",
            json={
                "tenant_id": tenant_id, "actor": actor, "action": action,
                "entity": entity, "entity_id": entity_id, "before": before, "after": after,
            },
            prefer="return=minimal",
        )
    except ApiError:
        pass


# ---------- score estimates (Module D) ----------
def count_cluster_outcomes(tenant_id: str, authority_cluster: str, category_cluster: str) -> int:
    rows = _rest(
        "GET", "outcomes",
        params={
            "tenant_id": f"eq.{tenant_id}",
            "authority_cluster": f"eq.{authority_cluster}",
            "category_cluster": f"eq.{category_cluster}",
            "select": "id",
        },
    ) or []
    return len(rows)


def save_estimate(tenant_id: str, tender_id: str, result: dict) -> None:
    _rest(
        "POST", "score_estimates",
        params={"on_conflict": "tender_id"},
        json={"tenant_id": tenant_id, "tender_id": tender_id, "result": result},
        prefer="resolution=merge-duplicates,return=minimal",
    )


def get_estimate(tender_id: str, tenant_id: str) -> dict | None:
    rows = _rest(
        "GET", "score_estimates",
        params={"tender_id": f"eq.{tender_id}", "tenant_id": f"eq.{tenant_id}", "select": "result"},
    )
    return rows[0]["result"] if rows else None
