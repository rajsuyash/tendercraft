"""Engine data access via Supabase PostgREST (service role).

The engine uses the service key, which BYPASSES RLS — so every function here MUST scope
by workspace_id explicitly (the code enforces what RLS would). A missing workspace filter is an
ET-6 defect (known-pitfalls: service-role bypasses RLS).
"""

from __future__ import annotations

from typing import Any

import httpx

from . import http
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
        r = http.client.request(
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


def create_tender(workspace_id: str, title: str) -> dict:
    rows = _rest("POST", "tenders", json={"workspace_id": workspace_id, "title": title})
    return rows[0]


def get_tender(tender_id: str, workspace_id: str) -> dict | None:
    rows = _rest(
        "GET", "tenders",
        params={"id": f"eq.{tender_id}", "workspace_id": f"eq.{workspace_id}", "select": "*"},
    )
    return rows[0] if rows else None


def insert_criteria(workspace_id: str, tender_id: str, criteria: list[dict]) -> list[dict]:
    payload = [{**c, "workspace_id": workspace_id, "tender_id": tender_id} for c in criteria]
    return _rest("POST", "criteria", json=payload) or []


def get_criteria(tender_id: str, workspace_id: str) -> list[dict]:
    return (
        _rest(
            "GET", "criteria",
            params={
                "tender_id": f"eq.{tender_id}",
                "workspace_id": f"eq.{workspace_id}",
                "select": "*",
            },
        )
        or []
    )


def confirm_criterion(criterion_id: str, workspace_id: str) -> list[dict]:
    return _rest(
        "PATCH", "criteria",
        params={"id": f"eq.{criterion_id}", "workspace_id": f"eq.{workspace_id}"},
        json={"confirmed": True},
    )


def get_criterion_in_tender(criterion_id: str, tender_id: str, workspace_id: str) -> dict | None:
    """Existence check that a criterion belongs to this tender AND this workspace — the guard on any
    write that binds a criterion (decisions, per-item doc links). One query covers ET-6."""
    rows = _rest(
        "GET", "criteria",
        params={
            "id": f"eq.{criterion_id}", "tender_id": f"eq.{tender_id}",
            "workspace_id": f"eq.{workspace_id}", "select": "id",
        },
    )
    return rows[0] if rows else None


def set_tender_locked(tender_id: str, workspace_id: str, locked_at: str) -> None:
    _rest(
        "PATCH", "tenders",
        params={"id": f"eq.{tender_id}", "workspace_id": f"eq.{workspace_id}"},
        json={"status": "locked", "locked_at": locked_at},
    )


# ---------- vendor profile (Module C) ----------
def get_profile_context(workspace_id: str) -> dict:
    """Assemble the full structured profile for eligibility evaluation."""
    scope = {"workspace_id": f"eq.{workspace_id}"}

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
def save_analysis(workspace_id: str, tender_id: str, result: dict) -> None:
    _rest(
        "POST", "analyses",
        params={"on_conflict": "tender_id"},
        json={"workspace_id": workspace_id, "tender_id": tender_id, "result": result},
        prefer="resolution=merge-duplicates",
    )


def get_analysis(tender_id: str, workspace_id: str) -> dict | None:
    rows = _rest(
        "GET", "analyses",
        params={
            "tender_id": f"eq.{tender_id}",
            "workspace_id": f"eq.{workspace_id}",
            "select": "result",
        },
    )
    return rows[0]["result"] if rows else None


# ---------- content library + proposals (Module B) ----------
def insert_library_document(workspace_id: str, doc: dict, uploaded_by: str | None) -> dict:
    rows = _rest(
        "POST", "library_documents",
        json={**doc, "workspace_id": workspace_id, "uploaded_by": uploaded_by},
    )
    return rows[0]


def get_valid_library_docs(workspace_id: str, today_iso: str) -> list[dict]:
    """Retrieval with the validity HARD-filter: expired docs are excluded (never a model choice)."""
    docs = _rest(
        "GET", "library_documents",
        params={
            "workspace_id": f"eq.{workspace_id}",
            "select": "id,name,doc_type,text_content,valid_to",
        },
    ) or []
    return [d for d in docs if not d.get("valid_to") or d["valid_to"] >= today_iso]


def create_proposal(workspace_id: str, tender_id: str) -> dict:
    rows = _rest(
        "POST", "proposals",
        params={"on_conflict": "tender_id"},
        json={"workspace_id": workspace_id, "tender_id": tender_id, "status": "draft"},
        prefer="resolution=merge-duplicates,return=representation",
    )
    return rows[0]


def upsert_response(workspace_id: str, proposal_id: str, criterion_id: str, resp: dict) -> None:
    _rest(
        "POST", "proposal_responses",
        params={"on_conflict": "proposal_id,criterion_id"},
        json={
            "workspace_id": workspace_id,
            "proposal_id": proposal_id,
            "criterion_id": criterion_id,
            **resp,
        },
        prefer="resolution=merge-duplicates",
    )


def get_proposal(proposal_id: str, workspace_id: str) -> dict | None:
    """Ownership guard for a caller-supplied proposal_id.

    Mirrors get_criterion_in_tender, which already guards this bug class on the readiness
    path: every write binding an id from the request must first prove that id belongs to
    the caller's workspace, because _rest uses the service role and RLS will not do it.
    """
    rows = _rest(
        "GET", "proposals",
        params={"id": f"eq.{proposal_id}", "workspace_id": f"eq.{workspace_id}",
                "select": "id,tender_id,status,approvals_required"},
    )
    return rows[0] if rows else None


def get_proposal_by_tender(tender_id: str, workspace_id: str) -> dict | None:
    rows = _rest(
        "GET", "proposals",
        params={
            "tender_id": f"eq.{tender_id}",
            "workspace_id": f"eq.{workspace_id}",
            "select": "*",
        },
    )
    return rows[0] if rows else None


def get_responses(proposal_id: str, workspace_id: str) -> list[dict]:
    return _rest(
        "GET", "proposal_responses",
        params={
            "proposal_id": f"eq.{proposal_id}",
            "workspace_id": f"eq.{workspace_id}",
            "select": "*",
        },
    ) or []


# ---------- long-form proposal sections (the document layer) ----------
def upsert_section(workspace_id: str, proposal_id: str, key: str, section: dict) -> None:
    _rest(
        "POST", "proposal_sections",
        # workspace_id in the conflict target: a service-role merge bypasses RLS, so without it
        # a caller-supplied proposal_id could reassign another workspace's row (see 0007).
        params={"on_conflict": "workspace_id,proposal_id,key"},
        json={"workspace_id": workspace_id, "proposal_id": proposal_id, "key": key, **section},
        prefer="resolution=merge-duplicates",
    )


def get_sections(proposal_id: str, workspace_id: str) -> list[dict]:
    return _rest(
        "GET", "proposal_sections",
        params={
            "proposal_id": f"eq.{proposal_id}", "workspace_id": f"eq.{workspace_id}",
            "select": "*", "order": "order_index.asc",
        },
    ) or []


def approve_section(
    workspace_id: str, proposal_id: str, key: str, approver: str, when_iso: str
) -> None:
    _rest(
        "PATCH", "proposal_sections",
        params={
            "proposal_id": f"eq.{proposal_id}",
            "workspace_id": f"eq.{workspace_id}",
            "key": f"eq.{key}",
        },
        json={"approved_by": approver, "approved_at": when_iso},
    )


def set_proposal_status(proposal_id: str, workspace_id: str, status: str) -> None:
    _rest(
        "PATCH", "proposals",
        params={"id": f"eq.{proposal_id}", "workspace_id": f"eq.{workspace_id}"},
        json={"status": status},
    )


# ---------- per-criterion readiness decisions (bidder resolve/ignore/do-not-proceed) ----------
def upsert_readiness_decision(
    workspace_id: str, tender_id: str, criterion_id: str, *,
    decision: str | None = None, comment: str | None = None,
    document_id: str | None = None, actor: str | None = None,
) -> dict:
    """Upsert one item's decision. Partial: only provided fields change; omitted ones keep their
    prior value on conflict (PostgREST merge only writes the columns in the payload)."""
    payload: dict[str, Any] = {
        "workspace_id": workspace_id, "tender_id": tender_id, "criterion_id": criterion_id,
    }
    if decision is not None:
        payload["decision"] = decision
    if comment is not None:
        payload["comment"] = comment
    if document_id is not None:
        payload["document_id"] = document_id
    if actor is not None:
        payload["updated_by"] = actor
    rows = _rest(
        "POST", "readiness_decisions",
        # workspace_id in the conflict target so a merge can never cross workspaces
        # (defense-in-depth behind the endpoint's ownership guard — the engine bypasses RLS).
        params={"on_conflict": "workspace_id,tender_id,criterion_id"},
        json=payload,
        prefer="resolution=merge-duplicates,return=representation",
    )
    return rows[0] if rows else {}


def get_readiness_decisions(tender_id: str, workspace_id: str) -> list[dict]:
    return _rest(
        "GET", "readiness_decisions",
        params={
            "tender_id": f"eq.{tender_id}",
            "workspace_id": f"eq.{workspace_id}",
            "select": "*",
        },
    ) or []


# ---------- approvals + audit + export (Module E) ----------
def get_approvals(proposal_id: str, workspace_id: str) -> list[dict]:
    return _rest(
        "GET", "proposal_approvals",
        params={
            "proposal_id": f"eq.{proposal_id}",
            "workspace_id": f"eq.{workspace_id}",
            "select": "*",
        },
    ) or []


def add_approval(workspace_id: str, proposal_id: str, stage: str, approver: str) -> None:
    _rest(
        "POST", "proposal_approvals",
        # workspace_id MUST lead the conflict target and match the unique key in 0009. This is
        # a service-role write, so RLS is bypassed and the key is the only workspace boundary:
        # without workspace_id here, a caller-supplied proposal_id merges onto another workspace's
        # row and reassigns it (see migrations/0009_approval_scope.sql).
        params={"on_conflict": "workspace_id,proposal_id,stage"},
        json={
            "workspace_id": workspace_id, "proposal_id": proposal_id,
            "stage": stage, "approver": approver,
        },
        prefer="resolution=merge-duplicates",
    )


def mark_exported(proposal_id: str, workspace_id: str, when_iso: str) -> None:
    _rest(
        "PATCH", "proposals",
        params={"id": f"eq.{proposal_id}", "workspace_id": f"eq.{workspace_id}"},
        json={"status": "exported", "exported_at": when_iso},
    )


def write_audit(
    workspace_id: str, actor: str | None, action: str, entity: str,
    entity_id: str | None, before: dict | None = None, after: dict | None = None,
) -> None:
    """Append an immutable audit event (E-FR4). Never fails the caller — audit is best-effort
    at the app layer, but the DB triggers guarantee it can't be altered once written."""
    try:
        _rest(
            "POST", "audit_events",
            json={
                "workspace_id": workspace_id, "actor": actor, "action": action,
                "entity": entity, "entity_id": entity_id, "before": before, "after": after,
            },
            prefer="return=minimal",
        )
    except ApiError:
        pass


# ---------- score estimates (Module D) ----------
def count_cluster_outcomes(workspace_id: str, authority_cluster: str, category_cluster: str) -> int:
    rows = _rest(
        "GET", "outcomes",
        params={
            "workspace_id": f"eq.{workspace_id}",
            "authority_cluster": f"eq.{authority_cluster}",
            "category_cluster": f"eq.{category_cluster}",
            "select": "id",
        },
    ) or []
    return len(rows)


def save_estimate(workspace_id: str, tender_id: str, result: dict) -> None:
    _rest(
        "POST", "score_estimates",
        params={"on_conflict": "tender_id"},
        json={"workspace_id": workspace_id, "tender_id": tender_id, "result": result},
        prefer="resolution=merge-duplicates,return=minimal",
    )


def get_estimate(tender_id: str, workspace_id: str) -> dict | None:
    rows = _rest(
        "GET", "score_estimates",
        params={
            "tender_id": f"eq.{tender_id}",
            "workspace_id": f"eq.{workspace_id}",
            "select": "result",
        },
    )
    return rows[0]["result"] if rows else None


# ---------- workspaces, membership, invitations ----------
def get_user_workspaces(user_id: str) -> list[dict]:
    """Every workspace this user belongs to — the switcher. One of only two places a SET
    of workspaces is the right answer; every data query stays scoped to the active one."""
    rows = _rest(
        "GET", "workspace_members",
        params={
            "user_id": f"eq.{user_id}",
            "select": "workspace_id,role,workspaces(id,name)",
        },
    ) or []
    return [
        {
            "id": r["workspace_id"],
            "name": (r.get("workspaces") or {}).get("name"),
            "role": r.get("role"),
        }
        for r in rows
    ]


def get_membership(user_id: str, workspace_id: str) -> dict | None:
    rows = _rest(
        "GET", "workspace_members",
        params={
            "user_id": f"eq.{user_id}",
            "workspace_id": f"eq.{workspace_id}",
            "select": "role",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


def get_workspace_members(workspace_id: str) -> list[dict]:
    """Roster with names. Two queries joined in Python rather than a PostgREST embed:
    workspace_members and profiles both reference auth.users but have no FK BETWEEN them,
    so `profiles(...)` is not an embeddable relationship and 400s."""
    rows = _rest(
        "GET", "workspace_members",
        params={
            "workspace_id": f"eq.{workspace_id}",
            "select": "user_id,role,created_at",
            "order": "created_at.asc",
        },
    ) or []
    if not rows:
        return []
    ids = ",".join(r["user_id"] for r in rows)
    people = _rest(
        "GET", "profiles",
        params={"user_id": f"in.({ids})", "select": "user_id,full_name,email"},
    ) or []
    by_id = {p["user_id"]: p for p in people}
    return [
        {
            "user_id": r["user_id"],
            "role": r["role"],
            "created_at": r.get("created_at"),
            "full_name": by_id.get(r["user_id"], {}).get("full_name"),
            "email": by_id.get(r["user_id"], {}).get("email"),
        }
        for r in rows
    ]


def count_workspace_admins(workspace_id: str) -> int:
    rows = _rest(
        "GET", "workspace_members",
        params={
            "workspace_id": f"eq.{workspace_id}",
            "role": "eq.admin",
            "select": "user_id",
        },
    ) or []
    return len(rows)


def add_workspace_member(user_id: str, workspace_id: str, role: str, added_by: str) -> None:
    _rest(
        "POST", "workspace_members",
        params={"on_conflict": "user_id,workspace_id"},
        json={"user_id": user_id, "workspace_id": workspace_id, "role": role,
              "added_by": added_by},
        prefer="resolution=merge-duplicates",
    )


def set_member_role(user_id: str, workspace_id: str, role: str) -> None:
    _rest(
        "PATCH", "workspace_members",
        params={"user_id": f"eq.{user_id}", "workspace_id": f"eq.{workspace_id}"},
        json={"role": role},
    )


def remove_workspace_member(user_id: str, workspace_id: str) -> None:
    _rest(
        "DELETE", "workspace_members",
        params={"user_id": f"eq.{user_id}", "workspace_id": f"eq.{workspace_id}"},
    )


def set_active_workspace(user_id: str, workspace_id: str) -> None:
    _rest(
        "PATCH", "profiles",
        params={"user_id": f"eq.{user_id}"},
        json={"active_workspace_id": workspace_id},
    )


def clear_active_workspace(user_id: str, workspace_id: str) -> None:
    """Null the active workspace only if it is the one being revoked — a member removed
    from workspace B must keep their active workspace A."""
    _rest(
        "PATCH", "profiles",
        params={"user_id": f"eq.{user_id}", "active_workspace_id": f"eq.{workspace_id}"},
        json={"active_workspace_id": None},
    )


def upsert_profile_identity(user_id: str, email: str, workspace_id: str) -> None:
    """Record who this person is, and give them an active workspace if they had none.

    full_name/email are denormalized from the verified JWT because auth.users is not
    readable through PostgREST — without them a roster renders truncated UUIDs.
    """
    existing = _rest(
        "GET", "profiles",
        params={"user_id": f"eq.{user_id}", "select": "active_workspace_id", "limit": "1"},
    )
    payload = {"user_id": user_id, "email": email}
    if not existing or not existing[0].get("active_workspace_id"):
        payload["active_workspace_id"] = workspace_id
    _rest(
        "POST", "profiles",
        params={"on_conflict": "user_id"},
        json=payload,
        prefer="resolution=merge-duplicates",
    )


def get_user_email(user_id: str) -> str | None:
    """Authoritative email from the auth system, for the invitation identity check."""
    s = get_settings()
    try:
        r = http.client.get(
            f"{s.supabase_url}/auth/v1/admin/users/{user_id}",
            headers=_headers(),
            timeout=10,
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise ApiError(502, "DB_ERROR", f"auth lookup failed: {exc}") from exc
    return (r.json() or {}).get("email")


def create_invitation(workspace_id: str, email: str, role: str, invited_by: str,
                      token_hash: str) -> None:
    # Replace any live invitation for this address rather than stacking them — the partial
    # unique index would reject the insert otherwise.
    _rest(
        "DELETE", "workspace_invitations",
        params={"workspace_id": f"eq.{workspace_id}", "email": f"eq.{email}",
                "accepted_at": "is.null"},
    )
    _rest(
        "POST", "workspace_invitations",
        json={"workspace_id": workspace_id, "email": email, "role": role,
              "invited_by": invited_by, "token_hash": token_hash},
    )


def get_invitation_by_hash(token_hash: str) -> dict | None:
    rows = _rest(
        "GET", "workspace_invitations",
        params={"token_hash": f"eq.{token_hash}", "select": "*", "limit": "1"},
    )
    return rows[0] if rows else None


def get_pending_invitations(workspace_id: str) -> list[dict]:
    return _rest(
        "GET", "workspace_invitations",
        params={
            "workspace_id": f"eq.{workspace_id}",
            "accepted_at": "is.null",
            # token_hash deliberately not selected — nothing outside the accept path needs it.
            "select": "id,email,role,expires_at,created_at",
            "order": "created_at.desc",
        },
    ) or []


def mark_invitation_accepted(invitation_id: str, user_id: str, when_iso: str) -> None:
    _rest(
        "PATCH", "workspace_invitations",
        params={"id": f"eq.{invitation_id}"},
        json={"accepted_at": when_iso, "accepted_by": user_id},
    )


# ---------- projects + portfolio ----------
def list_projects(workspace_id: str) -> list[dict]:
    return _rest(
        "GET", "projects",
        params={
            "workspace_id": f"eq.{workspace_id}",
            "select": "id,name,status,owner,created_at",
            "order": "created_at.desc",
        },
    ) or []


def create_project(workspace_id: str, name: str, owner: str | None) -> dict:
    rows = _rest(
        "POST", "projects",
        json={"workspace_id": workspace_id, "name": name, "owner": owner},
    )
    return rows[0]


def update_project(project_id: str, workspace_id: str, patch: dict) -> None:
    _rest(
        "PATCH", "projects",
        params={"id": f"eq.{project_id}", "workspace_id": f"eq.{workspace_id}"},
        json=patch,
    )


def get_project(project_id: str, workspace_id: str) -> dict | None:
    rows = _rest(
        "GET", "projects",
        params={"id": f"eq.{project_id}", "workspace_id": f"eq.{workspace_id}",
                "select": "*", "limit": "1"},
    )
    return rows[0] if rows else None


def make_cursor(row: dict) -> str:
    """Keyset cursor: "<created_at>|<id>".

    The id is NOT decoration. created_at alone is not unique — a bulk insert gives every
    row the same transaction timestamp, so `created_at < cursor` skips the entire rest of
    the page and pagination silently stops early. The tuple is the actual sort key.

    The Z suffix matters too: an unencoded '+' in a query string is read as a SPACE and
    httpx does not escape it, so a raw "+00:00" timestamp makes PostgREST 400.
    """
    ts = str(row["created_at"]).replace("+00:00", "Z").replace(" ", "T")
    return f"{ts}|{row['id']}"


def list_tenders(workspace_id: str, *, project_id: str | None = None, q: str | None = None,
                 status: str | None = None, cursor: str | None = None,
                 limit: int = 25) -> list[dict]:
    """Portfolio query: filter + search + KEYSET pagination.

    Keyset, not offset: offset re-reads rows and silently skips them when a concurrent
    insert shifts the window. Ordering is (created_at desc, id desc) so the cursor is
    total — created_at alone ties on bulk-seeded rows.
    """
    params = {
        "workspace_id": f"eq.{workspace_id}",
        "select": "id,title,tender_number,authority,status,deadline,project_id,created_at",
        "order": "created_at.desc,id.desc",
        "limit": str(limit),
    }
    if project_id:
        params["project_id"] = f"eq.{project_id}"
    if status:
        params["status"] = f"eq.{status}"
    if q:
        # `and=` so it composes with the keyset `or=` below instead of overwriting it.
        params["and"] = (
            f"(or(title.ilike.*{q}*,tender_number.ilike.*{q}*,authority.ilike.*{q}*))"
        )
    if cursor:
        ts, _, last_id = cursor.partition("|")
        # (created_at, id) < (ts, id) expressed for PostgREST: strictly earlier, OR the
        # same instant with a lower id. Matches the compound ORDER BY exactly.
        params["or"] = (
            f"(created_at.lt.{ts},and(created_at.eq.{ts},id.lt.{last_id}))"
        )
    return _rest("GET", "tenders", params=params) or []


def set_tender_project(tender_id: str, workspace_id: str, project_id: str | None) -> None:
    _rest(
        "PATCH", "tenders",
        params={"id": f"eq.{tender_id}", "workspace_id": f"eq.{workspace_id}"},
        json={"project_id": project_id},
    )


def get_workspace_by_name(org_id: str | None, name: str) -> dict | None:
    """Name collision check within an organization.

    Enforced here rather than by a DB constraint — see migrations/0015 for why. A firm
    running one workspace per client must not end up with two "Airtel" workspaces, because
    the name is the only thing distinguishing one client's data from another's in every
    switcher and page heading.
    """
    params = {"name": f"eq.{name}", "select": "id", "limit": "1"}
    params["org_id"] = f"eq.{org_id}" if org_id else "is.null"
    rows = _rest("GET", "workspaces", params=params)
    return rows[0] if rows else None


def create_workspace(name: str, org_id: str | None) -> dict:
    rows = _rest("POST", "workspaces", json={"name": name, "org_id": org_id})
    return rows[0]


# ---------- past bids + the answer library (G-FR3) ----------
def create_past_bid(workspace_id: str, bid: dict, uploaded_by: str | None) -> dict:
    rows = _rest(
        "POST", "past_bids",
        json={**bid, "workspace_id": workspace_id, "uploaded_by": uploaded_by},
    )
    return rows[0]


def get_past_bid(past_bid_id: str, workspace_id: str) -> dict | None:
    """Ownership guard for a caller-supplied bid id — the service role will not do it for us."""
    rows = _rest(
        "GET", "past_bids",
        params={"id": f"eq.{past_bid_id}", "workspace_id": f"eq.{workspace_id}", "select": "*"},
    )
    return rows[0] if rows else None


def list_past_bids(workspace_id: str) -> list[dict]:
    return _rest(
        "GET", "past_bids",
        params={"workspace_id": f"eq.{workspace_id}", "select": "*",
                "order": "created_at.desc"},
    ) or []


def set_past_bid_outcome(past_bid_id: str, workspace_id: str, outcome: str) -> None:
    _rest(
        "PATCH", "past_bids",
        params={"id": f"eq.{past_bid_id}", "workspace_id": f"eq.{workspace_id}"},
        json={"outcome": outcome},
    )


def upsert_answers(workspace_id: str, past_bid_id: str, rows: list[dict]) -> list[dict]:
    """Store mined pairs. Re-mining the same bid updates rather than duplicating."""
    if not rows:
        return []
    payload = [{**r, "workspace_id": workspace_id, "past_bid_id": past_bid_id} for r in rows]
    return _rest(
        "POST", "answers",
        params={"on_conflict": "workspace_id,past_bid_id,requirement_text"},
        json=payload,
        prefer="return=representation,resolution=merge-duplicates",
    ) or []


def get_answers_with_bids(workspace_id: str) -> list[dict]:
    """Every mined answer joined to the bid it shipped in — the input to reuse ranking.

    The join is what makes a suggestion a suggestion with a receipt: outcome, authority and
    date travel with the text, so the user is never asked to accept an anonymous paragraph.
    """
    rows = _rest(
        "GET", "answers",
        params={
            "workspace_id": f"eq.{workspace_id}",
            "select": "id,requirement_text,answer_text,section_key,category,past_bid_id,"
                      "past_bids(name,authority,submitted_on,outcome)",
        },
    ) or []
    out = []
    for r in rows:
        bid = r.pop("past_bids", None) or {}
        out.append({
            **r,
            "bid_name": bid.get("name"),
            "authority": bid.get("authority"),
            "submitted_on": bid.get("submitted_on"),
            "outcome": bid.get("outcome") or "unknown",
        })
    return out


def get_answer(answer_id: str, workspace_id: str) -> dict | None:
    rows = _rest(
        "GET", "answers",
        params={"id": f"eq.{answer_id}", "workspace_id": f"eq.{workspace_id}", "select": "*"},
    )
    return rows[0] if rows else None


def record_answer_usage(
    workspace_id: str, answer_id: str, proposal_id: str | None, target: str, actor: str | None,
) -> dict:
    """The G-AC6 receipt. Written by the accept path and by nothing else."""
    rows = _rest(
        "POST", "answer_usages",
        json={"workspace_id": workspace_id, "answer_id": answer_id,
              "proposal_id": proposal_id, "target": target, "actor": actor},
    )
    return rows[0]


def get_past_bid_texts(workspace_id: str) -> list[str]:
    """The prose of every past bid, for measuring house style. Text only — no metadata."""
    rows = _rest(
        "GET", "library_documents",
        params={"workspace_id": f"eq.{workspace_id}", "doc_type": "eq.past_proposal",
                "select": "text_content"},
    ) or []
    return [r.get("text_content") or "" for r in rows if (r.get("text_content") or "").strip()]


def upsert_style_profile(workspace_id: str, profile: dict, actor: str | None) -> dict:
    rows = _rest(
        "POST", "style_profiles",
        params={"on_conflict": "workspace_id"},
        json={"workspace_id": workspace_id, "built_by": actor, **profile},
        prefer="return=representation,resolution=merge-duplicates",
    )
    return rows[0] if rows else {}


def get_style_profile(workspace_id: str) -> dict | None:
    rows = _rest(
        "GET", "style_profiles",
        params={"workspace_id": f"eq.{workspace_id}", "select": "*", "limit": "1"},
    )
    return rows[0] if rows else None


def get_expired_library_docs(workspace_id: str, today_iso: str) -> list[dict]:
    """The inverse of get_valid_library_docs — what a reused answer may no longer claim."""
    docs = _rest(
        "GET", "library_documents",
        params={"workspace_id": f"eq.{workspace_id}", "select": "id,name,valid_to"},
    ) or []
    return [d for d in docs if d.get("valid_to") and d["valid_to"] < today_iso]


def get_profile(user_id: str) -> dict | None:
    rows = _rest(
        "GET", "profiles",
        params={"user_id": f"eq.{user_id}", "select": "org_id,is_org_admin", "limit": "1"},
    )
    return rows[0] if rows else None


def set_tender_meta(tender_id: str, workspace_id: str, tender_number: str | None,
                    authority: str | None) -> None:
    """Record identity read from the document itself. Only writes fields we actually found."""
    patch = {k: v for k, v in
             {"tender_number": tender_number, "authority": authority}.items() if v}
    if not patch:
        return
    _rest(
        "PATCH", "tenders",
        params={"id": f"eq.{tender_id}", "workspace_id": f"eq.{workspace_id}"},
        json=patch,
    )


# ---------- vendor profile writes (Module C) ----------
def upsert_vendor_profile(workspace_id: str, patch: dict) -> None:
    _rest(
        "POST", "vendor_profiles",
        params={"on_conflict": "workspace_id"},
        json={"workspace_id": workspace_id, **patch},
        prefer="resolution=merge-duplicates",
    )


def replace_profile_collection(workspace_id: str, table: str, rows: list[dict]) -> None:
    """Replace a whole profile sub-collection (financials / experience / certifications).

    Replace rather than per-row CRUD: these lists are short, the UI edits them as a set, and
    a diff-based API would need stable client-side ids for rows the user just typed. The
    delete is workspace-scoped, so it can never reach another workspace's rows.
    """
    _rest("DELETE", table, params={"workspace_id": f"eq.{workspace_id}"})
    if rows:
        _rest("POST", table, json=[{**r, "workspace_id": workspace_id} for r in rows])


def edit_section(workspace_id: str, proposal_id: str, key: str, body_md: str,
                 editor: str, when_iso: str) -> None:
    """Replace a section's prose with a human's own words.

    Clears flags and resets status: cite-or-flag judged MODEL output, and once a person has
    rewritten the text they own it — keeping an "unverified" flag raised against a sentence
    the model no longer wrote would be meaningless. Approval is deliberately NOT granted
    here; editing is authorship, sign-off is a separate act (and may be a separate person).
    """
    _rest(
        "PATCH", "proposal_sections",
        params={
            "proposal_id": f"eq.{proposal_id}",
            "workspace_id": f"eq.{workspace_id}",
            "key": f"eq.{key}",
        },
        json={
            "body_md": body_md,
            "word_count": len(body_md.split()),
            "status": "drafted",
            "flags": [],
            "edited_by": editor,
            "edited_at": when_iso,
            "approved_by": None,
            "approved_at": None,
        },
    )


def append_reused_section_text(
    workspace_id: str, proposal_id: str, key: str, text: str, validation: dict,
) -> None:
    """Add an accepted prior answer to a section, keeping the flags it came with.

    Deliberately NOT edit_section: that clears flags, because once a human has rewritten the
    prose they own it and a flag against text the model no longer wrote means nothing. A
    reused answer is the opposite case — nobody has re-written those sentences, and a claim
    inside them that no longer resolves must stay flagged until someone deals with it.

    Approval is cleared, as with any edit: a section that changed after sign-off needs signing
    off again.
    """
    rows = _rest(
        "GET", "proposal_sections",
        params={"proposal_id": f"eq.{proposal_id}", "workspace_id": f"eq.{workspace_id}",
                "key": f"eq.{key}", "select": "body_md,sentences,flags"},
    ) or []
    if not rows:
        raise ApiError(404, "SECTION_NOT_FOUND", f"section {key} not found on this proposal")
    current = rows[0]
    body = f"{(current.get('body_md') or '').rstrip()}\n\n{text.strip()}".strip()
    _rest(
        "PATCH", "proposal_sections",
        params={"proposal_id": f"eq.{proposal_id}", "workspace_id": f"eq.{workspace_id}",
                "key": f"eq.{key}"},
        json={
            "body_md": body,
            "word_count": len(body.split()),
            "sentences": (current.get("sentences") or []) + validation["sentences"],
            "flags": (current.get("flags") or []) + validation["flags"],
            # A section carrying an unresolved flag is 'unverified' whatever it was before.
            "status": "unverified" if validation["flags"] else "drafted",
            "approved_by": None,
            "approved_at": None,
        },
    )


# --- Module G: compliance matrix + the unmapped-requirement denominator ------------------


def insert_unmapped(workspace_id: str, tender_id: str, rows: list[dict]) -> list[dict]:
    """Persist the ingest-time requirement backlog (G-FR2).

    on_conflict names workspace_id alongside the natural key: the engine writes with the
    service role, which bypasses RLS, so a conflict target that omits the scope column can
    reassign another workspace's row (known-pitfalls).
    """
    # `document` is part of the key (migration 0026): the same sentence on page 4 of two
    # annexures is two unmapped requirements, and merging them undercounts the denominator.
    # Never NULL — Postgres treats NULLs as distinct, which would defeat the re-ingest guard.
    payload = [
        {**r, "document": r.get("document") or "", "workspace_id": workspace_id,
         "tender_id": tender_id}
        for r in rows
    ]
    return (
        _rest(
            "POST", "matrix_unmapped",
            params={"on_conflict": "workspace_id,tender_id,document,page,sentence"},
            json=payload,
            prefer="return=representation,resolution=merge-duplicates",
        )
        or []
    )


def get_unmapped(tender_id: str, workspace_id: str, only_open: bool = False) -> list[dict]:
    params = {
        "tender_id": f"eq.{tender_id}",
        "workspace_id": f"eq.{workspace_id}",
        "select": "*",
        "order": "page.asc,created_at.asc",
    }
    if only_open:
        params["resolution"] = "eq.open"
    return _rest("GET", "matrix_unmapped", params=params) or []


def resolve_unmapped(
    unmapped_id: str, workspace_id: str, resolution: str, actor: str, when_iso: str
) -> list[dict]:
    return (
        _rest(
            "PATCH", "matrix_unmapped",
            params={"id": f"eq.{unmapped_id}", "workspace_id": f"eq.{workspace_id}"},
            json={"resolution": resolution, "resolved_by": actor, "resolved_at": when_iso},
        )
        or []
    )


def upsert_matrix_rows(workspace_id: str, tender_id: str, rows: list[dict]) -> list[dict]:
    """Generate-or-refresh matrix rows. Existing human edits survive a regeneration.

    merge-duplicates on (workspace_id, tender_id, criterion_id) means re-running generation
    after a corrigendum refreshes the requirement text without wiping owners and statuses.
    """
    payload = [{**r, "workspace_id": workspace_id, "tender_id": tender_id} for r in rows]
    return (
        _rest(
            "POST", "matrix_rows",
            params={"on_conflict": "workspace_id,tender_id,criterion_id"},
            json=payload,
            prefer="return=representation,resolution=merge-duplicates",
        )
        or []
    )


def get_matrix_rows(tender_id: str, workspace_id: str) -> list[dict]:
    return (
        _rest(
            "GET", "matrix_rows",
            params={
                "tender_id": f"eq.{tender_id}",
                "workspace_id": f"eq.{workspace_id}",
                "select": "*",
                "order": "anchor_page.asc,created_at.asc",
            },
        )
        or []
    )


def update_matrix_row(row_id: str, tender_id: str, workspace_id: str, patch: dict) -> list[dict]:
    """Patch the editable fields of one row.

    tender_id is in the filter as well as the id: the id arrives from the caller, and a write
    that binds a caller-supplied id without proving it belongs to this tender AND workspace is
    the cross-workspace write this codebase has already been bitten by.
    """
    return (
        _rest(
            "PATCH", "matrix_rows",
            params={
                "id": f"eq.{row_id}",
                "tender_id": f"eq.{tender_id}",
                "workspace_id": f"eq.{workspace_id}",
            },
            json=patch,
        )
        or []
    )


# ---------- Module F: opportunities ----------
# The shared corpus has no workspace_id (migration 0019 explains why). Every workspace-shaped
# decision lives in opportunity_matches, which is RLS'd like everything else.


def upsert_opportunities(records: list[dict]) -> list[dict]:
    """Insert or refresh shared-corpus rows.

    `on_conflict` names BOTH columns of the unique constraint. Omitting one lets a service-role
    merge (which bypasses RLS) rewrite the wrong row — the upsert trap already documented in
    known-pitfalls, and here it would silently rewrite one tender with another's data.
    """
    if not records:
        return []
    return (
        _rest(
            "POST",
            "opportunities",
            params={"on_conflict": "source_id,portal_ref_no"},
            json=records,
            prefer="resolution=merge-duplicates,return=representation",
        )
        or []
    )


def get_opportunities(limit: int = 500, markets: list[str] | None = None) -> list[dict]:
    """The shared corpus, scoped to the countries the caller watches.

    A LIST rather than a single market: a bidder registered in one country routinely pursues
    tenders in another, and GeM's own listings carry `ba_is_global_tendering`. The caller
    always passes at least one — an empty list would silently mean "everything", which is the
    opposite of what a caller who lost their scope wants.
    """
    params = {"select": "*", "order": "closing_at.asc", "limit": str(limit)}
    if markets:
        params["market"] = "in.({})".format(",".join(sorted(set(markets))))
    return _rest("GET", "opportunities", params=params) or []


def get_workspace_market(workspace_id: str) -> str:
    """The HOME market: currency, statutory registers, timezone, explanation language.

    Exactly one, and not the same question as which feeds the workspace watches — see
    `get_workspace_markets` and migration 0022.
    """
    rows = _rest(
        "GET", "workspaces", params={"id": f"eq.{workspace_id}", "select": "market"}
    ) or []
    return (rows[0].get("market") if rows else None) or "IN"


def get_workspace_markets(workspace_id: str) -> list[str]:
    """Which countries feed this workspace's opportunity list.

    Falls back to the home market rather than to an empty list. A workspace that resolved to
    "watch nothing" would render an empty feed that looks exactly like "no tenders today" —
    the ET-7 failure with a friendly face — so there is no code path that can produce one.
    """
    rows = _rest(
        "GET",
        "workspaces",
        params={"id": f"eq.{workspace_id}", "select": "market,discovery_markets"},
    ) or []
    if not rows:
        return ["IN"]
    watched = rows[0].get("discovery_markets") or []
    return list(watched) or [rows[0].get("market") or "IN"]


def set_workspace_markets(workspace_id: str, markets: list[str]) -> list[str]:
    """Replace the watched set. The caller validates membership and the values."""
    rows = _rest(
        "PATCH",
        "workspaces",
        params={"id": f"eq.{workspace_id}"},
        json={"discovery_markets": markets},
    ) or []
    return list(rows[0].get("discovery_markets") or []) if rows else markets


def set_opportunity_eligibility(opportunity_id: str, fields: dict, at_iso: str) -> None:
    _rest(
        "PATCH",
        "opportunities",
        params={"id": f"eq.{opportunity_id}"},
        json={"eligibility": fields, "eligibility_at": at_iso},
        prefer="return=minimal",
    )


def get_discovery_rules(workspace_id: str) -> list[dict]:
    return (
        _rest(
            "GET",
            "discovery_rules",
            params={
                "workspace_id": f"eq.{workspace_id}",
                "select": "id,name,kind,spec,enabled",
                "order": "created_at.asc",
            },
        )
        or []
    )


def create_discovery_rule(workspace_id: str, rule: dict) -> dict:
    rows = _rest(
        "POST",
        "discovery_rules",
        params={"on_conflict": "workspace_id,name"},
        json={**rule, "workspace_id": workspace_id},
        prefer="resolution=merge-duplicates,return=representation",
    )
    return rows[0] if rows else {}


def update_discovery_rule(rule_id: str, workspace_id: str, patch: dict) -> None:
    """Scoped by workspace as well as id — a rule id from another workspace must not be
    patchable, and the service role bypasses RLS."""
    _rest(
        "PATCH",
        "discovery_rules",
        params={"id": f"eq.{rule_id}", "workspace_id": f"eq.{workspace_id}"},
        json=patch,
        prefer="return=minimal",
    )


def delete_discovery_rule(rule_id: str, workspace_id: str) -> None:
    _rest(
        "DELETE",
        "discovery_rules",
        params={"id": f"eq.{rule_id}", "workspace_id": f"eq.{workspace_id}"},
        prefer="return=minimal",
    )


def upsert_opportunity_matches(workspace_id: str, rows: list[dict]) -> int:
    """Bulk upsert. Every row is padded to the SAME key set first.

    PostgREST rejects a bulk insert whose objects have differing keys with a bare
    `400 Bad Request` — no column name, no hint. It bites here because only the in-scope rows
    carry relevance fields, so the payload is legitimately ragged the moment ranking exists.
    Filling the gaps with None writes an explicit null, which is what "not banded" means anyway.
    """
    if not rows:
        return 0
    keys = {k for r in rows for k in r} | {"workspace_id"}
    payload = [{**{k: None for k in keys}, **r, "workspace_id": workspace_id} for r in rows]
    _rest(
        "POST",
        "opportunity_matches",
        params={"on_conflict": "workspace_id,opportunity_id"},
        json=payload,
        prefer="resolution=merge-duplicates,return=minimal",
    )
    return len(payload)


def _market_scope(markets: list[str] | None) -> dict[str, str]:
    """PostgREST params that scope a `opportunity_matches` read to the watched countries.

    Scoping happens at READ time, not by deleting match rows when a country is unticked.
    That is deliberate: a match row carries the user's own state — whether they starred the
    tender, who it is assigned to — and deleting it would silently destroy a shortlist the
    moment someone toggled a country off, with no way back. An inner join costs one filter and
    keeps that state intact for when they toggle it on again.

    Every caller passes the SAME list, which is the actual defect this replaces: the recompute
    was scoped and the read was not, so narrowing the scope re-ranked the feed and filtered
    nothing, and 335 stale Indian rows outlived the choice to stop watching India.
    """
    if not markets:
        return {"select": "*,opportunities(*)"}
    return {
        # !inner turns the embed into a join, so the filter below can actually exclude a row
        # rather than merely nulling its embedded object.
        "select": "*,opportunities!inner(*)",
        "opportunities.market": "in.({})".format(",".join(sorted(set(markets)))),
    }


def get_feed(
    workspace_id: str, state: str, limit: int = 100, markets: list[str] | None = None
) -> list[dict]:
    """Feed rows with their shared-corpus opportunity embedded.

    One query, not N+1: a 50-row feed that lazily loaded each opportunity would be 51 round
    trips, and at the app-to-database latency this codebase has already been bitten by, that is
    the difference between a fast page and a broken-feeling one.
    """
    return (
        _rest(
            "GET",
            "opportunity_matches",
            params={
                "workspace_id": f"eq.{workspace_id}",
                "state": f"eq.{state}",
                **_market_scope(markets),
                # Best fit first, then the deadline that forces the decision. `nullsfirst` is
                # wrong here: an unbanded row is not the best match, it is an unknown one.
                "order": "relevance_band.asc.nullslast,computed_at.desc",
                "limit": str(limit),
            },
        )
        or []
    )


def _count_matches(
    workspace_id: str, filters: dict[str, str], markets: list[str] | None = None
) -> int:
    """Exact count of this workspace's match rows under `filters`, scoped to `markets`.

    One implementation for every counter on the coverage strip. There were three copies of this
    request and they differed only in one parameter; the strip's whole job is to read as ONE
    sentence about coverage, and three hand-maintained copies of the scoping logic is how two of
    its numbers end up describing different sets (docs/known-pitfalls.md: four counters
    describing one object will disagree).
    """
    s = get_settings()
    scope = _market_scope(markets)
    try:
        r = http.client.request(
            "GET",
            f"{s.supabase_url}/rest/v1/opportunity_matches",
            headers={**_headers(), "Prefer": "count=exact", "Range": "0-0"},
            params={
                "workspace_id": f"eq.{workspace_id}",
                **filters,
                **{k: v for k, v in scope.items() if k != "select"},
                # The join has to survive into the count, or the filter on the embedded
                # resource silently counts rows it was supposed to exclude.
                "select": "id,opportunities!inner(id)" if markets else "id",
            },
            timeout=15,
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise ApiError(502, "DB_ERROR", f"database request failed: {exc}") from exc
    return int((r.headers.get("Content-Range", "*/0")).split("/")[-1] or 0)


def count_feed(workspace_id: str, state: str, markets: list[str] | None = None) -> int:
    """Exact count for the Excluded bucket. F-FR12 requires the number to be always visible —
    "142 hidden by 3 of your rules" is the affordance that stops the feed feeling like a
    black box, so it cannot be approximated or omitted."""
    return _count_matches(workspace_id, {"state": f"eq.{state}"}, markets)


def count_comparable(workspace_id: str, markets: list[str] | None = None) -> int:
    """How many tenders in scope even STATE a turnover bar.

    Without it "0 below the turnover bar" is ambiguous in the worst direction: it reads as
    "nothing disqualifies you" when it may mean "nothing was measurable". On the French corpus
    today that distinction is the whole truth — 0 of 300 TED notices carry an extracted bar, so
    the zero says nothing at all and looked like an all-clear.
    """
    return _count_matches(
        workspace_id,
        {"opportunities.eligibility->>min_avg_annual_turnover_inr": "not.is.null"},
        # The filter is on the embedded resource, so the join must exist even when the caller
        # watches every market. Passing the scope through unconditionally guarantees it.
        markets or [],
    )


def get_relevance_hashes(workspace_id: str) -> dict[str, str]:
    """opportunity_id -> the relevance input hash already stored.

    The cost short-circuit: an unchanged hash means nothing the band depends on has changed, so
    the model is not asked again. One query rather than one per row.
    """
    rows = (
        _rest(
            "GET",
            "opportunity_matches",
            params={
                "workspace_id": f"eq.{workspace_id}",
                "select": "opportunity_id,relevance_input_hash",
                "relevance_input_hash": "not.is.null",
            },
        )
        or []
    )
    return {r["opportunity_id"]: r["relevance_input_hash"] for r in rows}


def count_eligible(
    workspace_id: str, markets: list[str] | None = None, signal: str = "likely_eligible"
) -> int:
    """Workspace-wide count of Depth-1 items carrying `signal`.

    The coverage strip asks for `likely_ineligible`, not `likely_eligible`. Measured across four
    real workspaces, the "clears the bar" figure disqualified nobody — 0 of 1,161 rows in three
    of them — because clearing a turnover bar only means your revenue is large enough, which is
    true of almost every row and decides nothing. The FAILING count is the rare, actionable one.

    Computed here rather than by counting the rows on the page. The coverage strip describes the
    WORKSPACE, so it must read the same whichever bucket is open; deriving it from the current
    bucket made it show 21 on In-scope and 0 on Excluded — two counters describing one object,
    disagreeing (docs/known-pitfalls.md).
    """
    return _count_matches(workspace_id, {"eligibility": f"eq.{signal}"}, markets)


def set_match_flags(
    workspace_id: str, opportunity_id: str, patch: dict
) -> list[dict]:
    return (
        _rest(
            "PATCH",
            "opportunity_matches",
            params={
                "workspace_id": f"eq.{workspace_id}",
                "opportunity_id": f"eq.{opportunity_id}",
            },
            json=patch,
        )
        or []
    )
