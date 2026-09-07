"""ET-6 for pursuits (0039) — the row that crosses the shared/private boundary.

A pursuit points at a SHARED `opportunities` row and a PRIVATE `tenders` row, which makes it
the one table in the system with a foot on each side. Two workspaces pursuing the same public
tender is normal and expected; either of them learning that the other is pursuing it is a
competitive disclosure, and for a consultant running two clients it is the F-US3 failure.

What this file pins, none of which unit tests with mocked `_rest` can reach:

  * both workspaces may pursue the SAME corpus row — the shared side still works
  * neither sees the other's pursuit, owner, state or linked tender — the private side holds
  * the unique key makes a second claim idempotent against a real database, not just in a mock
  * `pursuits_ingested_has_a_tender` is enforced by Postgres, so a state cannot claim an
    ingest that did not happen
  * a signed-in user cannot bind a pursuit to another workspace's tender

The last one is the whole reason the engine filters on workspace_id in `link_pursuit_tender`
even though it writes with the service role: RLS is the second line, and this proves the first
is not the only one.

Runs against the ephemeral stack only (`supabase start && ./tools/local-db.sh`). Never point
it at a shared project: `audit_events` is append-only, so the workspaces it creates are
permanently undeletable (docs/known-pitfalls.md).
"""

from __future__ import annotations

import pytest

from .conftest import (
    ANON_KEY,
    SERVICE_KEY,
    admin_create_user,
    admin_delete_user,
    admin_delete_users_by_email,
    grant_membership,
    requires_supabase,
    rest,
    sign_in,
)

PW = "Pursuit-Isolation-Pw-24!"
EMAIL_A = "pursuit-isolation-a@tendercraft.test"
EMAIL_B = "pursuit-isolation-b@tendercraft.test"

pytestmark = requires_supabase


@pytest.fixture(scope="module")
def two_workspaces_pursuing_one_tender():
    """Two workspaces, one shared corpus row, one pursuit each, one private tender in A."""
    users: list[str] = []
    workspaces: list[str] = []
    opportunity_id = None
    try:
        admin_delete_users_by_email(EMAIL_A, EMAIL_B)
        _, wa = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"name": "Pursuit Workspace A"})
        _, wb = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"name": "Pursuit Workspace B"})
        ws_a, ws_b = wa[0]["id"], wb[0]["id"]
        workspaces += [ws_a, ws_b]

        uid_a = admin_create_user(EMAIL_A, PW)
        uid_b = admin_create_user(EMAIL_B, PW)
        users += [uid_a, uid_b]
        grant_membership(uid_a, ws_a, email=EMAIL_A)
        grant_membership(uid_b, ws_b, email=EMAIL_B)

        _, opp = rest("POST", "opportunities", bearer=SERVICE_KEY, key=SERVICE_KEY,
                      body={"source_id": "test_portal",
                            "portal_ref_no": "TEST/PURSUIT/2026/1",
                            "title": "Shared public tender both want",
                            "authority": "Ministry of Testing"})
        opportunity_id = opp[0]["id"]

        # A has uploaded the package; B has claimed it and not uploaded yet. Two real states.
        _, ta = rest("POST", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"workspace_id": ws_a, "title": "A's private tender"})
        tender_a = ta[0]["id"]

        rest("POST", "pursuits", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"workspace_id": ws_a, "opportunity_id": opportunity_id,
                   "tender_id": tender_a, "state": "ingested"})
        rest("POST", "pursuits", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"workspace_id": ws_b, "opportunity_id": opportunity_id,
                   "state": "pursuing"})

        yield {"ws_a": ws_a, "ws_b": ws_b,
               "opportunity_id": opportunity_id, "tender_a": tender_a}
    finally:
        rest("DELETE", "pursuits", bearer=SERVICE_KEY, key=SERVICE_KEY,
             query=f"?opportunity_id=eq.{opportunity_id}" if opportunity_id else "?id=is.null")
        if opportunity_id:
            rest("DELETE", "opportunities", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 query=f"?id=eq.{opportunity_id}")
        for uid in users:
            admin_delete_user(uid)
        for ws in workspaces:
            rest("DELETE", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY, query=f"?id=eq.{ws}")


def test_both_workspaces_may_pursue_the_same_public_tender(two_workspaces_pursuing_one_tender):
    """Competitors bidding the same tender is the normal case, not a conflict to resolve."""
    for email in (EMAIL_A, EMAIL_B):
        token = sign_in(email, PW)
        _, rows = rest("GET", "pursuits", bearer=token, key=ANON_KEY, query="?select=*")
        assert len(rows) == 1, f"{email} cannot see their own pursuit"
        assert rows[0]["opportunity_id"] == two_workspaces_pursuing_one_tender["opportunity_id"]


def test_neither_workspace_sees_the_others_pursuit(two_workspaces_pursuing_one_tender):
    """That a competitor is bidding — and how far along — is exactly what must not leak."""
    ws_a = two_workspaces_pursuing_one_tender["ws_a"]
    ws_b = two_workspaces_pursuing_one_tender["ws_b"]

    token_a = sign_in(EMAIL_A, PW)
    _, a_rows = rest("GET", "pursuits", bearer=token_a, key=ANON_KEY, query="?select=*")
    assert [r["workspace_id"] for r in a_rows] == [ws_a]
    assert a_rows[0]["state"] == "ingested"

    token_b = sign_in(EMAIL_B, PW)
    _, b_rows = rest("GET", "pursuits", bearer=token_b, key=ANON_KEY, query="?select=*")
    assert [r["workspace_id"] for r in b_rows] == [ws_b]
    # The decisive one: B learns nothing about A's progress, including A's tender id.
    assert b_rows[0]["tender_id"] is None
    assert all(r["tender_id"] != two_workspaces_pursuing_one_tender["tender_a"] for r in b_rows)


def test_a_second_claim_is_the_same_pursuit(two_workspaces_pursuing_one_tender):
    """Idempotency against a real unique constraint, not a mocked `_rest`."""
    ws_b = two_workspaces_pursuing_one_tender["ws_b"]
    opp = two_workspaces_pursuing_one_tender["opportunity_id"]

    status, _ = rest(
        "POST", "pursuits", bearer=SERVICE_KEY, key=SERVICE_KEY,
        body={"workspace_id": ws_b, "opportunity_id": opp},
        query="?on_conflict=workspace_id,opportunity_id",
        # `prefer=`, not a Prefer in `headers` — the helper already sets one and a second
        # would be sent alongside it rather than replacing it.
        prefer="resolution=merge-duplicates",
    )
    assert status < 300

    _, rows = rest("GET", "pursuits", bearer=SERVICE_KEY, key=SERVICE_KEY,
                   query=f"?workspace_id=eq.{ws_b}&opportunity_id=eq.{opp}&select=id")
    assert len(rows) == 1, "a second claim created a second pursuit"


def test_a_state_cannot_claim_an_ingest_that_did_not_happen(two_workspaces_pursuing_one_tender):
    """`pursuits_ingested_has_a_tender`, enforced by Postgres rather than by the writer."""
    ws_b = two_workspaces_pursuing_one_tender["ws_b"]
    status, _ = rest("PATCH", "pursuits", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     query=f"?workspace_id=eq.{ws_b}", body={"state": "ingested"})
    assert status >= 400, "a pursuit claimed 'ingested' with no tender attached"


def test_a_user_cannot_bind_their_pursuit_to_another_workspaces_tender(
    two_workspaces_pursuing_one_tender,
):
    """B must not be able to reach A's tender id, even knowing it.

    RLS refuses the row; the engine also filters on workspace_id in `link_pursuit_tender`
    because it writes with the service role and RLS would not save it there.
    """
    token_b = sign_in(EMAIL_B, PW)
    tender_a = two_workspaces_pursuing_one_tender["tender_a"]

    status, _ = rest("PATCH", "pursuits", bearer=token_b, key=ANON_KEY,
                     query="?select=id", body={"tender_id": tender_a, "state": "ingested"})
    # Either refused outright, or accepted-and-matched-nothing. Both are safe; a 2xx that
    # actually wrote is not, so the row is re-read below rather than trusting the status.
    _, rows = rest("GET", "pursuits", bearer=SERVICE_KEY, key=SERVICE_KEY,
                   query=f"?tender_id=eq.{tender_a}&select=workspace_id")
    assert [r["workspace_id"] for r in rows] == [two_workspaces_pursuing_one_tender["ws_a"]], (
        f"B bound its pursuit to A's tender (PATCH returned {status})"
    )


def test_a_signed_in_user_cannot_write_a_pursuit_into_another_workspace(
    two_workspaces_pursuing_one_tender,
):
    """The `with check` half of the policy. Without it, a crafted body reaches another tenant."""
    token_b = sign_in(EMAIL_B, PW)
    ws_a = two_workspaces_pursuing_one_tender["ws_a"]
    opp = two_workspaces_pursuing_one_tender["opportunity_id"]

    status, _ = rest("POST", "pursuits", bearer=token_b, key=ANON_KEY,
                     body={"workspace_id": ws_a, "opportunity_id": opp})
    assert status >= 400, "a user inserted a pursuit into a workspace they do not belong to"
