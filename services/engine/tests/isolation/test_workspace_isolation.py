"""ET-6 workspace isolation — the zero-tolerance property, proven end-to-end against RLS.

Two workspaces, two users. Each user's authenticated session must see ONLY its own
workspace's rows; the service role (engine) sees all by design. A single cross-workspace
read here is a Sev-1 defect, so this suite is CI-blocking (PRD ET-6).
"""

from __future__ import annotations

import pytest

from .conftest import (
    ANON_KEY,
    SERVICE_KEY,
    admin_create_user,
    admin_delete_user,
    admin_delete_users_by_email,
    requires_supabase,
    rest,
    sign_in,
)

PW = "Isolation-Test-Pw-24!"
EMAIL_A = "isolation-a@tendercraft.test"
EMAIL_B = "isolation-b@tendercraft.test"


@pytest.fixture(scope="module")
def two_workspaces():
    """Provision workspace A/B, a user each, and one tender each. Torn down after."""
    created_users: list[str] = []
    workspace_ids: list[str] = []
    try:
        admin_delete_users_by_email(EMAIL_A, EMAIL_B)  # clear leftovers from any aborted run
        # service-role inserts (bypass RLS) to set up fixtures
        _, ta = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY, body={"name": "Workspace A"})
        _, tb = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY, body={"name": "Workspace B"})
        workspace_a, workspace_b = ta[0]["id"], tb[0]["id"]
        workspace_ids += [workspace_a, workspace_b]

        uid_a = admin_create_user(EMAIL_A, PW)
        uid_b = admin_create_user(EMAIL_B, PW)
        created_users += [uid_a, uid_b]

        rest("POST", "profiles", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"user_id": uid_a, "workspace_id": workspace_a, "role": "admin"})
        rest("POST", "profiles", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"user_id": uid_b, "workspace_id": workspace_b, "role": "admin"})

        rest("POST", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"workspace_id": workspace_a, "title": "Tender A — desktops"})
        rest("POST", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"workspace_id": workspace_b, "title": "Tender B — CCTV"})

        yield {"workspace_a": workspace_a, "workspace_b": workspace_b}
    finally:
        for uid in created_users:
            admin_delete_user(uid)
        for tid in workspace_ids:
            rest("DELETE", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 query=f"?workspace_id=eq.{tid}")
            rest("DELETE", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY, query=f"?id=eq.{tid}")


@requires_supabase
def test_user_sees_only_own_workspace_tenders(two_workspaces):
    jwt_a = sign_in(EMAIL_A, PW)
    status, rows = rest("GET", "tenders", bearer=jwt_a, key=ANON_KEY, query="?select=title,workspace_id")
    assert status == 200
    titles = {r["title"] for r in rows}
    assert titles == {"Tender A — desktops"}, f"cross-workspace leak: {titles}"
    assert all(r["workspace_id"] == two_workspaces["workspace_a"] for r in rows)


@requires_supabase
def test_other_user_sees_only_their_own(two_workspaces):
    jwt_b = sign_in(EMAIL_B, PW)
    status, rows = rest("GET", "tenders", bearer=jwt_b, key=ANON_KEY, query="?select=title")
    assert status == 200
    assert {r["title"] for r in rows} == {"Tender B — CCTV"}


@requires_supabase
def test_user_cannot_insert_into_another_workspace(two_workspaces):
    # RLS with-check must reject a workspace_id that isn't the caller's (ET-6 write side)
    jwt_a = sign_in(EMAIL_A, PW)
    status, _ = rest("POST", "tenders", bearer=jwt_a, key=ANON_KEY,
                     body={"workspace_id": two_workspaces["workspace_b"], "title": "smuggled"})
    assert status in (401, 403), f"expected RLS rejection, got {status}"


@requires_supabase
def test_service_role_sees_all_workspaces(two_workspaces):
    # the engine legitimately bypasses RLS; this documents that boundary
    status, rows = rest("GET", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY, query="?select=title")
    assert status == 200
    titles = {r["title"] for r in rows}
    assert {"Tender A — desktops", "Tender B — CCTV"} <= titles


@requires_supabase
def test_readiness_decision_is_workspace_scoped(two_workspaces):
    # A per-criterion decision for workspace A must never appear in workspace B's authed session (ET-6).
    workspace_a = two_workspaces["workspace_a"]
    _, td = rest("POST", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 body={"workspace_id": workspace_a, "title": "Tender A — decision scope"})
    tender_id = td[0]["id"]
    _, cr = rest("POST", "criteria", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 body={"workspace_id": workspace_a, "tender_id": tender_id,
                       "verbatim_text": "x", "category": "eligibility",
                       "requirement_level": "mandatory", "confidence": 0.9, "confirmed": True})
    rest("POST", "readiness_decisions", bearer=SERVICE_KEY, key=SERVICE_KEY,
         body={"workspace_id": workspace_a, "tender_id": tender_id, "criterion_id": cr[0]["id"],
               "decision": "ignore", "comment": "A-only"})

    jwt_b = sign_in(EMAIL_B, PW)
    status, rows = rest("GET", "readiness_decisions", bearer=jwt_b, key=ANON_KEY, query="?select=comment")
    assert status == 200
    assert rows == [], f"cross-workspace readiness-decision leak: {rows}"
    # teardown cascade (tenders delete by workspace_id) removes the tender/criterion/decision


@requires_supabase
def test_proposal_section_is_workspace_scoped(two_workspaces):
    # ET-6 for the document layer: a drafted section for workspace A must never surface in
    # workspace B's authed session. Long-form sections carry the bidder's actual strategy,
    # so a leak here is worse than a leaked criterion.
    workspace_a = two_workspaces["workspace_a"]
    _, td = rest("POST", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 body={"workspace_id": workspace_a, "title": "Tender A — section scope"})
    tender_id = td[0]["id"]
    _, pr = rest("POST", "proposals", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 body={"workspace_id": workspace_a, "tender_id": tender_id, "status": "draft"})
    rest("POST", "proposal_sections", bearer=SERVICE_KEY, key=SERVICE_KEY,
         body={"workspace_id": workspace_a, "proposal_id": pr[0]["id"], "key": "methodology",
               "heading": "Methodology", "order_index": 50, "kind": "narrative",
               "body_md": "A-only confidential approach"})

    jwt_b = sign_in(EMAIL_B, PW)
    status, rows = rest("GET", "proposal_sections", bearer=jwt_b, key=ANON_KEY,
                        query="?select=body_md")
    assert status == 200
    assert rows == [], f"cross-workspace proposal-section leak: {rows}"


@requires_supabase
def test_audit_events_are_immutable(two_workspaces):
    # E-AC1: append-only enforced at the DB, even for the service role
    _, rows = rest("POST", "audit_events", bearer=SERVICE_KEY, key=SERVICE_KEY,
                   body={"workspace_id": two_workspaces["workspace_a"], "action": "test", "entity": "tender"})
    event_id = rows[0]["id"]
    status, _ = rest("PATCH", "audit_events", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"action": "tampered"}, query=f"?id=eq.{event_id}")
    assert status >= 400, "audit_events must reject updates (append-only)"
    # DELETE must be rejected too — else a dropped trigger would pass on PATCH alone
    status, _ = rest("DELETE", "audit_events", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     query=f"?id=eq.{event_id}")
    assert status >= 400, "audit_events must reject deletes (append-only)"
    # the row is immutable, so leave it; the workspace teardown cascade removes it


@requires_supabase
def test_approval_write_cannot_reassign_another_workspaces_row(two_workspaces):
    """Sev-1 regression: a foreign proposal_id must not let workspace A capture B's approval.

    Calls the REAL db.add_approval so the test tracks the engine's actual on_conflict
    target rather than a hand-copied string. That write uses the SERVICE ROLE, so RLS is
    bypassed and the unique key is the only thing standing between workspaces: if it is just
    (proposal_id, stage), A's write resolves to DO UPDATE and rewrites workspace_id to A —
    silently stripping B's approval and making B's proposal non-exportable.
    """
    from app import db

    workspace_a, workspace_b = two_workspaces["workspace_a"], two_workspaces["workspace_b"]

    _, tb = rest("POST", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 body={"workspace_id": workspace_b, "title": "Tender B — approval scope"})
    _, pb = rest("POST", "proposals", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 body={"workspace_id": workspace_b, "tender_id": tb[0]["id"], "status": "draft"})
    proposal_b = pb[0]["id"]

    db.add_approval(workspace_b, proposal_b, "review", workspace_b)   # B approves its own
    db.add_approval(workspace_a, proposal_b, "review", workspace_a)   # A posts to B's proposal id

    _, rows = rest("GET", "proposal_approvals", bearer=SERVICE_KEY, key=SERVICE_KEY,
                   query=f"?proposal_id=eq.{proposal_b}&select=workspace_id,stage,approver")
    mine = [r for r in rows if r["workspace_id"] == workspace_b]
    assert len(mine) == 1, f"workspace B lost its own approval row: {rows}"
    assert mine[0]["approver"] == workspace_b, f"workspace B's approver was overwritten: {rows}"
