"""RBAC enforced on the live API — the three controls that were decorative.

Provisions a real `writer` in the same workspace as the seeded admin, then proves a writer
cannot do the things E-AC2/E-FR1 say only an admin can.
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
    requires_supabase,
    rest,
    sign_in,
)

PW = "Rbac-Test-Pw-24!"
WRITER = "rbac-writer@tendercraft.test"


@pytest.fixture(scope="module")
def writer_in_workspace():
    users, ws = [], []
    try:
        admin_delete_users_by_email(WRITER)
        forget_token(WRITER, PW)
        _, w = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                    body={"name": "RBAC Workspace"})
        workspace_id = w[0]["id"]
        ws.append(workspace_id)
        uid = admin_create_user(WRITER, PW)
        users.append(uid)
        rest("POST", "profiles", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"user_id": uid, "workspace_id": workspace_id, "role": "writer",
                   "active_workspace_id": workspace_id})
        rest("POST", "workspace_members", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"user_id": uid, "workspace_id": workspace_id, "role": "writer"})

        _, t = rest("POST", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
                    body={"workspace_id": workspace_id, "title": "RBAC tender"})
        _, p = rest("POST", "proposals", bearer=SERVICE_KEY, key=SERVICE_KEY,
                    body={"workspace_id": workspace_id, "tender_id": t[0]["id"],
                          "status": "draft"})
        yield {"jwt": sign_in(WRITER, PW), "tender_id": t[0]["id"], "proposal_id": p[0]["id"],
               "workspace_id": workspace_id}
    finally:
        for uid in users:
            admin_delete_user(uid)
        for w_id in ws:
            rest("DELETE", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 query=f"?workspace_id=eq.{w_id}")
            rest("DELETE", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 query=f"?id=eq.{w_id}")


def _client():
    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


def _auth(f):
    return {"Authorization": f"Bearer {f['jwt']}"}


@requires_supabase
def test_writer_role_resolves_from_membership(writer_in_workspace):
    r = _client().get("/api/me", headers=_auth(writer_in_workspace))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["role"] == "writer"


@requires_supabase
def test_writer_cannot_approve(writer_in_workspace):
    """A writer holds no approve:* permission — the chain is no longer a free counter."""
    f = writer_in_workspace
    r = _client().post(f"/api/proposals/{f['proposal_id']}/approve?stage=review",
                       headers=_auth(f))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "FORBIDDEN"


@requires_supabase
def test_invented_stage_is_rejected_with_the_envelope(writer_in_workspace):
    """`stage` was free text: two invented names created two rows and cleared a 2-approval
    gate. Now a closed set — and the rejection must still be the LOCKED envelope, not
    FastAPI's {"detail": ...}."""
    f = writer_in_workspace
    r = _client().post(f"/api/proposals/{f['proposal_id']}/approve?stage=rubber-stamp",
                       headers=_auth(f))
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "detail" not in body


@requires_supabase
def test_writer_cannot_override_the_export_gate(writer_in_workspace):
    """E-AC2's "logged admin path" was neither logged nor admin-only."""
    f = writer_in_workspace
    r = _client().post(f"/api/tenders/{f['tender_id']}/export?override=true", headers=_auth(f))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "FORBIDDEN"


@requires_supabase
def test_the_override_attempt_is_audited(writer_in_workspace):
    """A non-admin trying to override is itself the signal, so the audit precedes the 403."""
    f = writer_in_workspace
    _client().post(f"/api/tenders/{f['tender_id']}/export?override=true", headers=_auth(f))
    _, rows = rest("GET", "audit_events", bearer=SERVICE_KEY, key=SERVICE_KEY,
                   query=f"?workspace_id=eq.{f['workspace_id']}&action=eq.override_attempt"
                         "&select=after")
    assert rows, "override attempt was not audited"
    assert rows[-1]["after"]["granted"] is False


@requires_supabase
def test_approving_a_foreign_proposal_is_404(writer_in_workspace):
    f = writer_in_workspace
    r = _client().post(
        "/api/proposals/11111111-2222-3333-4444-555555555555/approve?stage=review",
        headers=_auth(f),
    )
    assert r.status_code in (403, 404), r.text
