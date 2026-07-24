"""ET-6 tenant isolation — the zero-tolerance property, proven end-to-end against RLS.

Two tenants, two users. Each user's authenticated session must see ONLY its own
tenant's rows; the service role (engine) sees all by design. A single cross-tenant
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
def two_tenants():
    """Provision tenant A/B, a user each, and one tender each. Torn down after."""
    created_users: list[str] = []
    tenant_ids: list[str] = []
    try:
        admin_delete_users_by_email(EMAIL_A, EMAIL_B)  # clear leftovers from any aborted run
        # service-role inserts (bypass RLS) to set up fixtures
        _, ta = rest("POST", "tenants", bearer=SERVICE_KEY, key=SERVICE_KEY, body={"name": "Tenant A"})
        _, tb = rest("POST", "tenants", bearer=SERVICE_KEY, key=SERVICE_KEY, body={"name": "Tenant B"})
        tenant_a, tenant_b = ta[0]["id"], tb[0]["id"]
        tenant_ids += [tenant_a, tenant_b]

        uid_a = admin_create_user(EMAIL_A, PW)
        uid_b = admin_create_user(EMAIL_B, PW)
        created_users += [uid_a, uid_b]

        rest("POST", "profiles", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"user_id": uid_a, "tenant_id": tenant_a, "role": "admin"})
        rest("POST", "profiles", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"user_id": uid_b, "tenant_id": tenant_b, "role": "admin"})

        rest("POST", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"tenant_id": tenant_a, "title": "Tender A — desktops"})
        rest("POST", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"tenant_id": tenant_b, "title": "Tender B — CCTV"})

        yield {"tenant_a": tenant_a, "tenant_b": tenant_b}
    finally:
        for uid in created_users:
            admin_delete_user(uid)
        for tid in tenant_ids:
            rest("DELETE", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 query=f"?tenant_id=eq.{tid}")
            rest("DELETE", "tenants", bearer=SERVICE_KEY, key=SERVICE_KEY, query=f"?id=eq.{tid}")


@requires_supabase
def test_user_sees_only_own_tenant_tenders(two_tenants):
    jwt_a = sign_in(EMAIL_A, PW)
    status, rows = rest("GET", "tenders", bearer=jwt_a, key=ANON_KEY, query="?select=title,tenant_id")
    assert status == 200
    titles = {r["title"] for r in rows}
    assert titles == {"Tender A — desktops"}, f"cross-tenant leak: {titles}"
    assert all(r["tenant_id"] == two_tenants["tenant_a"] for r in rows)


@requires_supabase
def test_other_user_sees_only_their_own(two_tenants):
    jwt_b = sign_in(EMAIL_B, PW)
    status, rows = rest("GET", "tenders", bearer=jwt_b, key=ANON_KEY, query="?select=title")
    assert status == 200
    assert {r["title"] for r in rows} == {"Tender B — CCTV"}


@requires_supabase
def test_user_cannot_insert_into_another_tenant(two_tenants):
    # RLS with-check must reject a tenant_id that isn't the caller's (ET-6 write side)
    jwt_a = sign_in(EMAIL_A, PW)
    status, _ = rest("POST", "tenders", bearer=jwt_a, key=ANON_KEY,
                     body={"tenant_id": two_tenants["tenant_b"], "title": "smuggled"})
    assert status in (401, 403), f"expected RLS rejection, got {status}"


@requires_supabase
def test_service_role_sees_all_tenants(two_tenants):
    # the engine legitimately bypasses RLS; this documents that boundary
    status, rows = rest("GET", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY, query="?select=title")
    assert status == 200
    titles = {r["title"] for r in rows}
    assert {"Tender A — desktops", "Tender B — CCTV"} <= titles


@requires_supabase
def test_audit_events_are_immutable(two_tenants):
    # E-AC1: append-only enforced at the DB, even for the service role
    _, rows = rest("POST", "audit_events", bearer=SERVICE_KEY, key=SERVICE_KEY,
                   body={"tenant_id": two_tenants["tenant_a"], "action": "test", "entity": "tender"})
    event_id = rows[0]["id"]
    status, _ = rest("PATCH", "audit_events", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"action": "tampered"}, query=f"?id=eq.{event_id}")
    assert status >= 400, "audit_events must reject updates (append-only)"
    # DELETE must be rejected too — else a dropped trigger would pass on PATCH alone
    status, _ = rest("DELETE", "audit_events", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     query=f"?id=eq.{event_id}")
    assert status >= 400, "audit_events must reject deletes (append-only)"
    # the row is immutable, so leave it; the tenant teardown cascade removes it
