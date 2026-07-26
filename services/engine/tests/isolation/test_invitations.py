"""Getting a second human into a workspace — the flow that did not exist.

Before this, onboarding meant running a dev-only seed script that deleted the user first.
These run the whole cycle against the live project with two real auth users: invite →
accept → roster → role change → deprovision.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from .conftest import (
    SERVICE_KEY,
    admin_create_user,
    admin_delete_user,
    admin_delete_users_by_email,
    forget_token,
    grant_membership,
    requires_supabase,
    rest,
    sign_in,
)

PW = "Invite-Test-Pw-24!"
ADMIN = "invite-admin@tendercraft.test"
INVITEE = "invite-joiner@tendercraft.test"
INTRUDER = "invite-intruder@tendercraft.test"


@pytest.fixture(scope="module")
def workspace_with_admin():
    users, ws = [], []
    try:
        admin_delete_users_by_email(ADMIN, INVITEE, INTRUDER)
        forget_token(ADMIN, PW)
        forget_token(INVITEE, PW)
        forget_token(INTRUDER, PW)
        _, w = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                    body={"name": "Invite Workspace"})
        workspace_id = w[0]["id"]
        ws.append(workspace_id)

        admin_uid = admin_create_user(ADMIN, PW)
        users.append(admin_uid)
        grant_membership(admin_uid, workspace_id, "admin", email=ADMIN, org_admin=True)

        # The invitee and intruder exist but belong to nothing yet.
        invitee_uid = admin_create_user(INVITEE, PW)
        intruder_uid = admin_create_user(INTRUDER, PW)
        users += [invitee_uid, intruder_uid]

        yield {"workspace_id": workspace_id, "admin_uid": admin_uid,
               "invitee_uid": invitee_uid, "intruder_uid": intruder_uid}
    finally:
        for uid in users:
            admin_delete_user(uid)
        for w_id in ws:
            rest("DELETE", "workspace_invitations", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 query=f"?workspace_id=eq.{w_id}")
            rest("DELETE", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 query=f"?id=eq.{w_id}")


def _client():
    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


def _hdr(email):
    return {"Authorization": f"Bearer {sign_in(email, PW)}"}


def _invite(f, email=INVITEE, role="writer"):
    return _client().post(
        f"/api/workspaces/{f['workspace_id']}/invitations",
        json={"email": email, "role": role}, headers=_hdr(ADMIN),
    )


@requires_supabase
def test_admin_can_invite_and_gets_the_token_once(workspace_with_admin):
    r = _invite(workspace_with_admin)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["token"]


@requires_supabase
def test_only_the_hash_is_persisted(workspace_with_admin):
    """A database read must not be replayable into workspace membership."""
    token = _invite(workspace_with_admin).json()["data"]["token"]
    _, rows = rest("GET", "workspace_invitations", bearer=SERVICE_KEY, key=SERVICE_KEY,
                   query=f"?workspace_id=eq.{workspace_with_admin['workspace_id']}"
                         "&select=token_hash")
    assert rows
    assert all(r["token_hash"] != token for r in rows)


@requires_supabase
def test_a_forwarded_invitation_cannot_be_redeemed_by_someone_else(workspace_with_admin):
    """The email check IS the security of this flow. Without it the link is a bearer token
    for membership — forwarded once in Outlook, an outsider joins a client engagement."""
    token = _invite(workspace_with_admin).json()["data"]["token"]
    r = _client().post("/api/invitations/accept", json={"token": token},
                       headers=_hdr(INTRUDER))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "INVITATION_EMAIL_MISMATCH"


@requires_supabase
def test_a_bad_token_is_not_found(workspace_with_admin):
    r = _client().post("/api/invitations/accept", json={"token": "nope"},
                       headers=_hdr(INTRUDER))
    assert r.status_code == 404


@requires_supabase
def test_accept_joins_the_workspace_and_the_roster_renders_two_people(workspace_with_admin):
    f = workspace_with_admin
    token = _invite(f).json()["data"]["token"]

    r = _client().post("/api/invitations/accept", json={"token": token},
                       headers=_hdr(INVITEE))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["role"] == "writer"

    # The roster was structurally capped at one row before profiles_roster existed.
    r = _client().get(f"/api/workspaces/{f['workspace_id']}/members", headers=_hdr(ADMIN))
    assert r.status_code == 200, r.text
    members = r.json()["data"]["members"]
    # Assert the PROPERTY (the roster shows more than one person, with identity and role)
    # rather than an exact count — sibling tests in this module-scoped fixture add and
    # remove the same invitee, so a hard count couples this test to their order.
    assert len(members) >= 2, members
    by_email = {m["email"]: m for m in members}
    assert INVITEE in by_email, members
    assert by_email[INVITEE]["role"] == "writer"
    assert ADMIN in by_email, "the inviting admin should still be on the roster"


@requires_supabase
def test_the_invitation_cannot_be_reused(workspace_with_admin):
    f = workspace_with_admin
    token = _invite(f).json()["data"]["token"]
    assert _client().post("/api/invitations/accept", json={"token": token},
                          headers=_hdr(INVITEE)).status_code == 200
    r = _client().post("/api/invitations/accept", json={"token": token},
                       headers=_hdr(INVITEE))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INVITATION_USED"


@requires_supabase
def test_a_writer_cannot_invite(workspace_with_admin):
    f = workspace_with_admin
    token = _invite(f).json()["data"]["token"]
    _client().post("/api/invitations/accept", json={"token": token}, headers=_hdr(INVITEE))
    r = _client().post(f"/api/workspaces/{f['workspace_id']}/invitations",
                       json={"email": "someone@example.test"}, headers=_hdr(INVITEE))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


@requires_supabase
def test_the_last_admin_cannot_be_demoted(workspace_with_admin):
    f = workspace_with_admin
    r = _client().patch(
        f"/api/workspaces/{f['workspace_id']}/members/{f['admin_uid']}",
        json={"role": "writer"}, headers=_hdr(ADMIN),
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "LAST_ADMIN"


@requires_supabase
def test_deprovisioning_removes_all_access_immediately(workspace_with_admin):
    """Deleting the membership row is sufficient AND complete — the resolver validates
    against it on every request, so scope goes NULL on the very next call. The user and
    their audit trail survive, because audit_events is append-only."""
    f = workspace_with_admin
    token = _invite(f).json()["data"]["token"]
    _client().post("/api/invitations/accept", json={"token": token}, headers=_hdr(INVITEE))

    assert _client().get("/api/me", headers=_hdr(INVITEE)).status_code == 200

    r = _client().delete(
        f"/api/workspaces/{f['workspace_id']}/members/{f['invitee_uid']}",
        headers=_hdr(ADMIN),
    )
    assert r.status_code == 200, r.text

    after = _client().get("/api/me", headers=_hdr(INVITEE))
    assert after.status_code == 403
    assert after.json()["error"]["code"] in ("NO_WORKSPACE", "NOT_A_MEMBER")

    # The person still exists; only the membership went.
    _, rows = rest("GET", "profiles", bearer=SERVICE_KEY, key=SERVICE_KEY,
                   query=f"?user_id=eq.{f['invitee_uid']}&select=user_id,email")
    assert rows, "deprovisioning must not delete the user"


# --- workspace creation (the gap: previously only a service-role script could do it) ---


def _cleanup_created(new_id: str, home_id: str, user_id: str) -> None:
    """Delete a workspace created by a test AND put the creator back in the fixture one.

    create_workspace switches the caller into the new workspace, so deleting it without
    restoring leaves active_workspace_id dangling — the caller then resolves to NULL scope
    and every later test in this module 403s. (Not reachable in the product: there is no
    delete-workspace endpoint. Worth knowing before one is added.)
    """
    rest("PATCH", "profiles", bearer=SERVICE_KEY, key=SERVICE_KEY,
         query=f"?user_id=eq.{user_id}", body={"active_workspace_id": home_id})
    rest("DELETE", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY, query=f"?id=eq.{new_id}")


@requires_supabase
def test_org_admin_can_create_a_workspace_and_lands_in_it(workspace_with_admin):
    """End of the "onboarding is a script" gap. Creating must also grant membership, or the
    creator makes a workspace that current_workspace_id() cannot resolve for them."""
    import uuid

    f = workspace_with_admin
    name = f"Create Test {uuid.uuid4().hex[:8]}"
    r = _client().post("/api/workspaces", json={"name": name}, headers=_hdr(ADMIN))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == name
    assert data["role"] == "admin"

    # Membership was granted and the caller was switched into it.
    me = _client().get("/api/me", headers=_hdr(ADMIN))
    assert me.status_code == 200
    assert me.json()["data"]["workspace_id"] == data["id"]

    ws = _client().get("/api/workspaces", headers=_hdr(ADMIN)).json()["data"]
    assert data["id"] in {w["id"] for w in ws["workspaces"]}

    _cleanup_created(data["id"], f["workspace_id"], f["admin_uid"])


@requires_supabase
def test_duplicate_workspace_name_is_rejected(workspace_with_admin):
    """No DB constraint (see migrations/0015), so this check is the only thing preventing a
    firm from ending up with two workspaces called "Airtel"."""
    import uuid

    f = workspace_with_admin
    name = f"Dup Test {uuid.uuid4().hex[:8]}"
    first = _client().post("/api/workspaces", json={"name": name}, headers=_hdr(ADMIN))
    assert first.status_code == 200, first.text
    again = _client().post("/api/workspaces", json={"name": name}, headers=_hdr(ADMIN))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "WORKSPACE_EXISTS"
    _cleanup_created(first.json()["data"]["id"], f["workspace_id"], f["admin_uid"])


@requires_supabase
def test_a_non_org_admin_cannot_create_a_workspace(workspace_with_admin):
    f = workspace_with_admin
    token = _invite(f).json()["data"]["token"]
    _client().post("/api/invitations/accept", json={"token": token}, headers=_hdr(INVITEE))
    r = _client().post("/api/workspaces", json={"name": "Should Not Exist"},
                       headers=_hdr(INVITEE))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "FORBIDDEN"
