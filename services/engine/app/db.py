"""Engine data access via Supabase PostgREST (service role).

The engine uses the service key, which BYPASSES RLS — so every function here MUST scope
by workspace_id explicitly (the code enforces what RLS would). A missing workspace filter is an
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
        r = httpx.get(
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
