"""Data access via Supabase PostgREST with the service role.

The service role BYPASSES RLS, so every function here MUST scope by authority_id explicitly —
the code enforces what the policy would. A missing authority filter is a cross-authority read.

NOTE the deliberate duplication with the bidder engine's db.py. There is no shared module and
there will not be one: a "shared" data-access layer is precisely how the F13 wall dies.
"""

from __future__ import annotations

from typing import Any

import httpx

from . import http
from .config import get_settings
from .envelope import ApiError


def _headers() -> dict[str, str]:
    key = get_settings().service_key
    if not key:
        raise ApiError(500, "ENGINE_MISCONFIGURED", "service key not configured")
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def rest(method: str, path: str, *, params: dict | None = None, json: Any = None,
         prefer: str = "return=representation") -> Any:
    s = get_settings()
    try:
        r = http.client.request(
            method, f"{s.supabase_url}/rest/v1/{path}",
            headers={**_headers(), "Prefer": prefer}, params=params, json=json,
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise ApiError(502, "DB_ERROR", f"database request failed: {exc}") from exc
    return r.json() if r.text else None


def one(rows: list | None) -> dict | None:
    return rows[0] if rows else None


# ── tenancy ────────────────────────────────────────────────────────────────────
def member_for(user_id: str, authority_id: str | None) -> dict | None:
    """The caller's membership. Mirrors current_authority_id() in SQL — header-preferred,
    always validated against authority_members. Two implementations of one rule; drift
    between them is a cross-authority read."""
    params = {"user_id": f"eq.{user_id}", "select": "authority_id,role", "limit": "1"}
    if authority_id:
        params["authority_id"] = f"eq.{authority_id}"
    else:
        prof = one(rest("GET", "profiles", params={
            "user_id": f"eq.{user_id}", "select": "active_authority_id", "limit": "1"}))
        if not prof or not prof.get("active_authority_id"):
            return None
        params["authority_id"] = f"eq.{prof['active_authority_id']}"
    return one(rest("GET", "authority_members", params=params))


def authority(authority_id: str) -> dict | None:
    return one(rest("GET", "authorities",
                    params={"id": f"eq.{authority_id}", "select": "*", "limit": "1"}))


# ── evaluations ────────────────────────────────────────────────────────────────
def evaluations(authority_id: str) -> list[dict]:
    return rest("GET", "evaluations", params={
        "authority_id": f"eq.{authority_id}", "select": "*", "order": "created_at.desc"}) or []


def evaluation(eval_id: str, authority_id: str) -> dict | None:
    return one(rest("GET", "evaluations", params={
        "id": f"eq.{eval_id}", "authority_id": f"eq.{authority_id}", "select": "*", "limit": "1"}))


def update_evaluation(eval_id: str, authority_id: str, patch: dict) -> None:
    rest("PATCH", "evaluations",
         params={"id": f"eq.{eval_id}", "authority_id": f"eq.{authority_id}"}, json=patch)


def criteria(eval_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "criteria", params={
        "evaluation_id": f"eq.{eval_id}", "authority_id": f"eq.{authority_id}",
        "select": "*", "order": "order_index.asc"}) or []


def bids(eval_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "bids", params={
        "evaluation_id": f"eq.{eval_id}", "authority_id": f"eq.{authority_id}",
        "select": "*", "order": "bidder_name.asc"}) or []


def responses(eval_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "bid_responses", params={
        "authority_id": f"eq.{authority_id}",
        "select": "*,bids!inner(evaluation_id)",
        "bids.evaluation_id": f"eq.{eval_id}"}) or []


def scores(eval_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "scores", params={
        "evaluation_id": f"eq.{eval_id}", "authority_id": f"eq.{authority_id}",
        "select": "*"}) or []


def consensus(eval_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "consensus_marks", params={
        "evaluation_id": f"eq.{eval_id}", "authority_id": f"eq.{authority_id}",
        "select": "*"}) or []


def members(authority_id: str) -> list[dict]:
    return rest("GET", "authority_members", params={
        "authority_id": f"eq.{authority_id}", "select": "*", "order": "role.asc"}) or []


def coi(eval_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "coi_declarations", params={
        "evaluation_id": f"eq.{eval_id}", "authority_id": f"eq.{authority_id}",
        "select": "*"}) or []


def financials(eval_id: str, authority_id: str) -> list[dict]:
    """Reads prices with the SERVICE ROLE, which bypasses the RLS seal. Every caller must
    have already passed gates.financial_readable(); this function is deliberately named so
    that an unguarded call stands out in review."""
    return rest("GET", "bid_financials", params={
        "authority_id": f"eq.{authority_id}",
        "select": "*,bids!inner(evaluation_id)",
        "bids.evaluation_id": f"eq.{eval_id}"}) or []


def upsert_score(row: dict) -> None:
    rest("POST", "scores", params={"on_conflict": "bid_id,criterion_id,evaluator_id"},
         json=row, prefer="resolution=merge-duplicates")


def upsert_consensus(row: dict) -> None:
    rest("POST", "consensus_marks", params={"on_conflict": "bid_id,criterion_id"},
         json=row, prefer="resolution=merge-duplicates")


def upsert_coi(row: dict) -> None:
    rest("POST", "coi_declarations", params={"on_conflict": "evaluation_id,user_id"},
         json=row, prefer="resolution=merge-duplicates")


def set_responsive(bid_id: str, authority_id: str, patch: dict) -> None:
    rest("PATCH", "bids", params={"id": f"eq.{bid_id}", "authority_id": f"eq.{authority_id}"},
         json=patch)


def open_financial(bid_id: str, authority_id: str, patch: dict) -> None:
    rest("PATCH", "bid_financials",
         params={"bid_id": f"eq.{bid_id}", "authority_id": f"eq.{authority_id}"}, json=patch)


def insert_tie_break(row: dict) -> None:
    rest("POST", "tie_break_decisions", json=row)


def audit(authority_id: str, eval_id: str | None, actor: str | None, action: str,
          entity: str | None = None, entity_id: str | None = None,
          detail: dict | None = None) -> None:
    rest("POST", "audit_events", json={
        "authority_id": authority_id, "evaluation_id": eval_id, "actor_id": actor,
        "action": action, "entity": entity, "entity_id": entity_id, "detail": detail,
    }, prefer="return=minimal")


def audit_events(eval_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "audit_events", params={
        "evaluation_id": f"eq.{eval_id}", "authority_id": f"eq.{authority_id}",
        "select": "*", "order": "created_at.desc", "limit": "200"}) or []
