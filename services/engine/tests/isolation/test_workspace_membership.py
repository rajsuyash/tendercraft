"""Multi-workspace isolation (ET-6) — the executable definition of the property.

Replaces the old "every row I can see carries MY one workspace_id" assertion, which is
false by design once a user holds two memberships. The property is now:

    a user sees rows from exactly ONE workspace — the active one — and that workspace must
    be one they are a member of.

Two of these are load-bearing:
  * a forged header for a non-member workspace resolves to NULL, so every table returns
    zero rows — not the victim's rows, and not the attacker's either. Fails CLOSED.
  * the engine (service role, RLS bypassed) and RLS resolve the same header to the same
    workspace. Those are two implementations of one rule, and drift between them is the
    top residual risk of the scalar-resolver design.
"""

from __future__ import annotations

import pytest

from .conftest import (
    ANON_KEY,
    SERVICE_KEY,
    admin_create_user,
    admin_delete_user,
    admin_delete_users_by_email,
    forget_token,
    requires_supabase,
    rest,
    sign_in,
)

PW = "Membership-Test-Pw-24!"
EMAIL = "membership-multi@tendercraft.test"
OUTSIDER = "membership-outsider@tendercraft.test"


@pytest.fixture(scope="module")
def user_in_two_workspaces():
    """One user, member of workspaces A and B. A third workspace C they are NOT in."""
    users: list[str] = []
    ws: list[str] = []
    try:
        admin_delete_users_by_email(EMAIL, OUTSIDER)
        forget_token(EMAIL, PW)
        forget_token(OUTSIDER, PW)
        ids = []
        for name in ("Membership A", "Membership B", "Membership C"):
            _, w = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                        body={"name": name})
            ids.append(w[0]["id"])
        a, b, c = ids
        ws += ids

        uid = admin_create_user(EMAIL, PW)
        users.append(uid)
        rest("POST", "profiles", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"user_id": uid, "workspace_id": a, "role": "admin",
                   "active_workspace_id": a})
        for w_id in (a, b):
            rest("POST", "workspace_members", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 body={"user_id": uid, "workspace_id": w_id, "role": "admin"})

        # One distinguishable tender per workspace, including the one they cannot reach.
        for w_id, title in ((a, "Tender in A"), (b, "Tender in B"), (c, "Tender in C")):
            rest("POST", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 body={"workspace_id": w_id, "title": title})

        yield {"user_id": uid, "a": a, "b": b, "c": c}
    finally:
        for uid in users:
            admin_delete_user(uid)
        for w_id in ws:
            rest("DELETE", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 query=f"?workspace_id=eq.{w_id}")
            rest("DELETE", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 query=f"?id=eq.{w_id}")


def _titles(jwt, header=None):
    q = "?select=title"
    status, rows = rest("GET", "tenders", bearer=jwt, key=ANON_KEY, query=q, headers=header)
    assert status == 200, rows
    return {r["title"] for r in rows}


@requires_supabase
def test_active_workspace_scopes_reads(user_in_two_workspaces):
    """Member of A and B, active = A -> sees ONLY A. Membership alone does not grant sight."""
    jwt = sign_in(EMAIL, PW)
    assert _titles(jwt) == {"Tender in A"}


@requires_supabase
def test_switching_active_changes_scope(user_in_two_workspaces):
    f = user_in_two_workspaces
    rest("PATCH", "profiles", bearer=SERVICE_KEY, key=SERVICE_KEY,
         query=f"?user_id=eq.{f['user_id']}", body={"active_workspace_id": f["b"]})
    try:
        assert _titles(sign_in(EMAIL, PW)) == {"Tender in B"}
    finally:
        rest("PATCH", "profiles", bearer=SERVICE_KEY, key=SERVICE_KEY,
             query=f"?user_id=eq.{f['user_id']}", body={"active_workspace_id": f["a"]})


@requires_supabase
def test_header_selects_a_workspace_you_belong_to(user_in_two_workspaces):
    f = user_in_two_workspaces
    jwt = sign_in(EMAIL, PW)
    assert _titles(jwt, {"x-workspace-id": f["b"]}) == {"Tender in B"}


@requires_supabase
def test_forged_header_for_a_non_member_workspace_yields_nothing(user_in_two_workspaces):
    """The security property: an unreachable workspace resolves to NULL, so EVERY table
    returns zero rows — not C's rows, and not A's either. Fails closed, silently, safely."""
    f = user_in_two_workspaces
    jwt = sign_in(EMAIL, PW)
    assert _titles(jwt, {"x-workspace-id": f["c"]}) == set()
    assert _titles(jwt, {"x-workspace-id": "11111111-2222-3333-4444-555555555555"}) == set()


@requires_supabase
def test_switcher_lists_only_workspaces_you_belong_to(user_in_two_workspaces):
    jwt = sign_in(EMAIL, PW)
    status, rows = rest("GET", "workspaces", bearer=jwt, key=ANON_KEY, query="?select=name")
    assert status == 200
    assert {r["name"] for r in rows} == {"Membership A", "Membership B"}


@requires_supabase
def test_roster_does_not_recurse(user_in_two_workspaces):
    """workspace_members' roster policy calls a function that reads workspace_members.

    A 42P17 infinite-recursion surfaces as a 500, so a 200 here IS the guarantee. This is
    why the bootstrap policy must stay a bare column comparison and the table must never
    set FORCE ROW LEVEL SECURITY.
    """
    jwt = sign_in(EMAIL, PW)
    status, rows = rest("GET", "workspace_members", bearer=jwt, key=ANON_KEY,
                        query="?select=user_id,role")
    assert status == 200, f"policy recursion or denial: {rows}"
    assert len(rows) >= 1


@requires_supabase
def test_revoking_membership_immediately_removes_all_access(user_in_two_workspaces):
    """Deprovisioning is one DELETE — no extra code. The resolver validates against
    membership on every request, so scope goes NULL on the very next call."""
    f = user_in_two_workspaces
    rest("DELETE", "workspace_members", bearer=SERVICE_KEY, key=SERVICE_KEY,
         query=f"?user_id=eq.{f['user_id']}&workspace_id=eq.{f['a']}")
    try:
        assert _titles(sign_in(EMAIL, PW)) == set()
    finally:
        rest("POST", "workspace_members", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"user_id": f["user_id"], "workspace_id": f["a"], "role": "admin"})


@requires_supabase
def test_engine_and_rls_agree_on_the_same_header(user_in_two_workspaces):
    """Closes the two-implementations drift: RLS resolves the scope in SQL, the engine
    resolves it in Python with the service role. They must never disagree."""
    from fastapi.testclient import TestClient

    from app.main import app

    f = user_in_two_workspaces
    jwt = sign_in(EMAIL, PW)

    resp = TestClient(app).get("/api/me", headers={"Authorization": f"Bearer {jwt}"})
    assert resp.status_code == 200, resp.text
    engine_ws = resp.json()["data"]["workspace_id"]

    status, rows = rest("GET", "workspaces", bearer=jwt, key=ANON_KEY,
                        query="?select=id", headers={"x-workspace-id": engine_ws})
    assert status == 200
    assert engine_ws in {r["id"] for r in rows}, "engine resolved a workspace RLS disagrees with"
    assert engine_ws == f["a"]
