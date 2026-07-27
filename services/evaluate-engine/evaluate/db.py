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


# ── tenders ────────────────────────────────────────────────────────────────
def tenders(authority_id: str, include_archived: bool = False) -> list[dict]:
    """Active tenders by default.

    Archived is the only removal this product has: audit_events is append-only, so a tender
    that has been audited can never be deleted — the cascade is refused even to the service
    role. Filtering here is what keeps a concluded or abandoned tender out of the officer's
    dashboard without pretending it is gone."""
    params = {"authority_id": f"eq.{authority_id}", "select": "*", "order": "created_at.desc"}
    if not include_archived:
        params["state"] = "neq.archived"
    return rest("GET", "tenders", params=params) or []


def tender(tender_id: str, authority_id: str) -> dict | None:
    return one(rest("GET", "tenders", params={
        "id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}",
        "select": "*", "limit": "1"}))


def update_tender(tender_id: str, authority_id: str, patch: dict) -> None:
    rest("PATCH", "tenders",
         params={"id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}"}, json=patch)


def criteria(tender_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "criteria", params={
        "tender_id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}",
        "select": "*", "order": "order_index.asc"}) or []


def bids(tender_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "bids", params={
        "tender_id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}",
        "select": "*", "order": "bidder_name.asc"}) or []


def responses(tender_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "bid_responses", params={
        "authority_id": f"eq.{authority_id}",
        "select": "*,bids!inner(tender_id)",
        "bids.tender_id": f"eq.{tender_id}"}) or []


def scores(tender_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "scores", params={
        "tender_id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}",
        "select": "*"}) or []


def consensus(tender_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "consensus_marks", params={
        "tender_id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}",
        "select": "*"}) or []


def members(authority_id: str) -> list[dict]:
    return rest("GET", "authority_members", params={
        "authority_id": f"eq.{authority_id}", "select": "*", "order": "role.asc"}) or []


def coi(tender_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "coi_declarations", params={
        "tender_id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}",
        "select": "*"}) or []


def financials(tender_id: str, authority_id: str) -> list[dict]:
    """Reads prices with the SERVICE ROLE, which bypasses the RLS seal. Every caller must
    have already passed gates.financial_readable(); this function is deliberately named so
    that an unguarded call stands out in review."""
    return rest("GET", "bid_financials", params={
        "authority_id": f"eq.{authority_id}",
        "select": "*,bids!inner(tender_id)",
        "bids.tender_id": f"eq.{tender_id}"}) or []


def upsert_score(row: dict) -> None:
    rest("POST", "scores", params={"on_conflict": "bid_id,criterion_id,evaluator_id"},
         json=row, prefer="resolution=merge-duplicates")


def upsert_consensus(row: dict) -> None:
    rest("POST", "consensus_marks", params={"on_conflict": "bid_id,criterion_id"},
         json=row, prefer="resolution=merge-duplicates")


def upsert_coi(row: dict) -> None:
    rest("POST", "coi_declarations", params={"on_conflict": "tender_id,user_id"},
         json=row, prefer="resolution=merge-duplicates")


def set_responsive(bid_id: str, authority_id: str, patch: dict) -> None:
    rest("PATCH", "bids", params={"id": f"eq.{bid_id}", "authority_id": f"eq.{authority_id}"},
         json=patch)


def open_financial(bid_id: str, authority_id: str, patch: dict) -> None:
    rest("PATCH", "bid_financials",
         params={"bid_id": f"eq.{bid_id}", "authority_id": f"eq.{authority_id}"}, json=patch)


def insert_tie_break(row: dict) -> None:
    rest("POST", "tie_break_decisions", json=row)


def audit(authority_id: str, tender_id: str | None, actor: str | None, action: str,
          entity: str | None = None, entity_id: str | None = None,
          detail: dict | None = None) -> None:
    rest("POST", "audit_events", json={
        "authority_id": authority_id, "tender_id": tender_id, "actor_id": actor,
        "action": action, "entity": entity, "entity_id": entity_id, "detail": detail,
    }, prefer="return=minimal")


def audit_events(tender_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "audit_events", params={
        "tender_id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}",
        "select": "*", "order": "created_at.desc", "limit": "200"}) or []


# ── ingestion writes ───────────────────────────────────────────────────────────
def create_tender(authority_id: str, row: dict) -> dict:
    return one(rest("POST", "tenders", json={**row, "authority_id": authority_id}))


def insert_criteria(authority_id: str, tender_id: str, rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    payload = [{**r, "authority_id": authority_id, "tender_id": tender_id} for r in rows]
    return rest("POST", "criteria", json=payload) or []


def update_criterion(criterion_id: str, authority_id: str, patch: dict) -> None:
    rest("PATCH", "criteria",
         params={"id": f"eq.{criterion_id}", "authority_id": f"eq.{authority_id}"}, json=patch)


def delete_criterion(criterion_id: str, authority_id: str) -> None:
    rest("DELETE", "criteria",
         params={"id": f"eq.{criterion_id}", "authority_id": f"eq.{authority_id}"},
         prefer="return=minimal")


def create_bid(authority_id: str, tender_id: str, bidder_name: str) -> dict:
    return one(rest("POST", "bids", json={
        "authority_id": authority_id, "tender_id": tender_id, "bidder_name": bidder_name}))


def upsert_responses(authority_id: str, rows: list[dict]) -> None:
    if not rows:
        return
    rest("POST", "bid_responses", params={"on_conflict": "bid_id,criterion_id"},
         json=[{**r, "authority_id": authority_id} for r in rows],
         prefer="resolution=merge-duplicates,return=minimal")


def insert_financial(authority_id: str, bid_id: str, amount) -> None:
    """Written at ingest and immediately unreadable — the RLS policy on bid_financials keys on
    the tender's technical_locked_at, so the row exists long before anyone may see it."""
    rest("POST", "bid_financials", params={"on_conflict": "bid_id"},
         json={"authority_id": authority_id, "bid_id": bid_id, "amount_inr": amount},
         prefer="resolution=merge-duplicates,return=minimal")


# ── bulk intake (F14/F15) ──────────────────────────────────────────────────────
def bid_files(tender_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "bid_files", params={
        "tender_id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}",
        "select": "*", "order": "created_at.asc"}) or []


def file_by_hash(tender_id: str, authority_id: str, sha256: str) -> dict | None:
    """The idempotency lookup behind F14-AC3. Content, not filename."""
    return one(rest("GET", "bid_files", params={
        "tender_id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}",
        "sha256": f"eq.{sha256}", "select": "*", "limit": "1"}))


def insert_bid_file(authority_id: str, tender_id: str, row: dict) -> dict | None:
    return one(rest("POST", "bid_files",
                    json={**row, "authority_id": authority_id, "tender_id": tender_id}))


def update_bid_file(file_id: str, authority_id: str, patch: dict) -> None:
    rest("PATCH", "bid_files",
         params={"id": f"eq.{file_id}", "authority_id": f"eq.{authority_id}"}, json=patch)


def attributions(tender_id: str, authority_id: str) -> list[dict]:
    """Joined through bid_files so the tender filter is enforced in the query, not in Python."""
    return rest("GET", "file_attributions", params={
        "authority_id": f"eq.{authority_id}",
        "select": "*,bid_files!inner(tender_id,filename,status)",
        "bid_files.tender_id": f"eq.{tender_id}"}) or []


def upsert_attribution(authority_id: str, row: dict) -> None:
    rest("POST", "file_attributions", params={"on_conflict": "file_id"},
         json={**row, "authority_id": authority_id},
         prefer="resolution=merge-duplicates,return=minimal")


def bid_by_name(tender_id: str, authority_id: str, bidder_name: str) -> dict | None:
    return one(rest("GET", "bids", params={
        "tender_id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}",
        "bidder_name": f"eq.{bidder_name}", "select": "*", "limit": "1"}))


def get_bid(bid_id: str, tender_id: str, authority_id: str) -> dict | None:
    """Ownership check before any write binding a caller-supplied bid id.

    The bidder product paid for this one: binding a caller-supplied id to a row without
    checking it belongs to the caller's tenant AND tender is a cross-tenant write.
    """
    return one(rest("GET", "bids", params={
        "id": f"eq.{bid_id}", "tender_id": f"eq.{tender_id}",
        "authority_id": f"eq.{authority_id}", "select": "*", "limit": "1"}))


# ── required documents (F17/F18) ───────────────────────────────────────────────
def required_documents(tender_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "required_documents", params={
        "tender_id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}",
        "select": "*", "order": "order_index.asc"}) or []


def replace_required_documents(authority_id: str, tender_id: str, rows: list[dict]) -> list[dict]:
    """Replace the register wholesale. Only reachable before the register freezes (F17-AC2)."""
    rest("DELETE", "required_documents",
         params={"tender_id": f"eq.{tender_id}", "authority_id": f"eq.{authority_id}"},
         prefer="return=minimal")
    if not rows:
        return []
    payload = [{**r, "authority_id": authority_id, "tender_id": tender_id} for r in rows]
    return rest("POST", "required_documents", json=payload) or []


def document_presence(tender_id: str, authority_id: str) -> list[dict]:
    """Human overrides only. The computed verdict is never stored — see documents.py."""
    return rest("GET", "document_presence", params={
        "authority_id": f"eq.{authority_id}",
        "select": "*,required_documents!inner(tender_id)",
        "required_documents.tender_id": f"eq.{tender_id}"}) or []


def upsert_document_override(authority_id: str, row: dict) -> None:
    rest("POST", "document_presence", params={"on_conflict": "requirement_id,bid_id"},
         json={**row, "authority_id": authority_id},
         prefer="resolution=merge-duplicates,return=minimal")


def get_requirement(requirement_id: str, tender_id: str, authority_id: str) -> dict | None:
    """Ownership check before binding a caller-supplied requirement id to a write."""
    return one(rest("GET", "required_documents", params={
        "id": f"eq.{requirement_id}", "tender_id": f"eq.{tender_id}",
        "authority_id": f"eq.{authority_id}", "select": "*", "limit": "1"}))


# ── drafts (F22–F26) ───────────────────────────────────────────────────────────
def drafts(authority_id: str) -> list[dict]:
    return rest("GET", "drafts", params={
        "authority_id": f"eq.{authority_id}", "select": "*",
        "order": "created_at.desc"}) or []


def draft(draft_id: str, authority_id: str) -> dict | None:
    return one(rest("GET", "drafts", params={
        "id": f"eq.{draft_id}", "authority_id": f"eq.{authority_id}",
        "select": "*", "limit": "1"}))


def create_draft(authority_id: str, row: dict) -> dict | None:
    return one(rest("POST", "drafts", json={**row, "authority_id": authority_id}))


def update_draft(draft_id: str, authority_id: str, patch: dict) -> None:
    rest("PATCH", "drafts",
         params={"id": f"eq.{draft_id}", "authority_id": f"eq.{authority_id}"}, json=patch)


def draft_criteria(draft_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "draft_criteria", params={
        "draft_id": f"eq.{draft_id}", "authority_id": f"eq.{authority_id}",
        "select": "*", "order": "order_index.asc"}) or []


def replace_draft_criteria(authority_id: str, draft_id: str, rows: list[dict]) -> list[dict]:
    rest("DELETE", "draft_criteria",
         params={"draft_id": f"eq.{draft_id}", "authority_id": f"eq.{authority_id}"},
         prefer="return=minimal")
    if not rows:
        return []
    return rest("POST", "draft_criteria",
                json=[{**r, "authority_id": authority_id, "draft_id": draft_id}
                      for r in rows]) or []


def draft_reviews(draft_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "draft_reviews", params={
        "draft_id": f"eq.{draft_id}", "authority_id": f"eq.{authority_id}",
        "select": "*", "order": "reviewer_role.asc"}) or []


def upsert_draft_review(authority_id: str, row: dict) -> None:
    rest("POST", "draft_reviews", params={"on_conflict": "draft_id,reviewer_role"},
         json={**row, "authority_id": authority_id},
         prefer="resolution=merge-duplicates,return=minimal")


def invalidate_draft_signoffs(draft_id: str, authority_id: str) -> None:
    """A sign-off on a document that then changed is not a sign-off (F25-AC4)."""
    rest("PATCH", "draft_reviews", params={
        "draft_id": f"eq.{draft_id}", "authority_id": f"eq.{authority_id}",
        "signed_off_at": "not.is.null", "invalidated_at": "is.null",
    }, json={"invalidated_at": "now()"}, prefer="return=minimal")


def draft_dismissals(draft_id: str, authority_id: str) -> list[dict]:
    return rest("GET", "draft_finding_dismissals", params={
        "draft_id": f"eq.{draft_id}", "authority_id": f"eq.{authority_id}",
        "select": "*"}) or []


def dismiss_finding(authority_id: str, row: dict) -> None:
    rest("POST", "draft_finding_dismissals",
         params={"on_conflict": "draft_id,rule_id,target_id"},
         json={**row, "authority_id": authority_id},
         prefer="resolution=merge-duplicates,return=minimal")
