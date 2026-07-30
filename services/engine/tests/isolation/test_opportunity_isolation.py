"""ET-6 for the shared corpus — the test that earns migration 0019's exception.

`opportunities` deliberately has NO workspace_id, which breaks the rule that every table is
workspace-scoped. This suite proves the exception is safe rather than merely convenient, and it
is the only evidence that justifies the shape:

  * both workspaces read the SAME public corpus rows — that is the point, one crawl for everyone
  * neither can see the other's decisions, rules, verdicts, or watch state
  * neither can WRITE to the shared corpus, so one customer cannot poison another's feed
  * the G-9 check constraint holds against a real database, not just in unit tests

If someone later "tidies up" by adding a workspace_id to opportunities, or by relaxing the check
constraint, this file is what fails.
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

PW = "Opportunity-Isolation-Pw-24!"
EMAIL_A = "opp-isolation-a@tendercraft.test"
EMAIL_B = "opp-isolation-b@tendercraft.test"

pytestmark = requires_supabase


@pytest.fixture(scope="module")
def two_workspaces_one_corpus():
    """Two workspaces, two users, ONE shared opportunity with a decision recorded per side."""
    users: list[str] = []
    workspaces: list[str] = []
    opportunity_id = None
    try:
        admin_delete_users_by_email(EMAIL_A, EMAIL_B)
        _, wa = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"name": "Opp Workspace A"})
        _, wb = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"name": "Opp Workspace B"})
        ws_a, ws_b = wa[0]["id"], wb[0]["id"]
        workspaces += [ws_a, ws_b]

        uid_a = admin_create_user(EMAIL_A, PW)
        uid_b = admin_create_user(EMAIL_B, PW)
        users += [uid_a, uid_b]
        grant_membership(uid_a, ws_a, email=EMAIL_A)
        grant_membership(uid_b, ws_b, email=EMAIL_B)

        # One public tender, inserted once by the service role — exactly as ingest does.
        _, opp = rest("POST", "opportunities", bearer=SERVICE_KEY, key=SERVICE_KEY,
                      body={"source_id": "test_portal",
                            "portal_ref_no": "TEST/ISO/2026/1",
                            "title": "Shared public tender",
                            "authority": "Ministry of Testing"})
        opportunity_id = opp[0]["id"]

        # A's rule hides it; B's feed keeps it. Same tender, opposite decisions.
        rest("POST", "discovery_rules", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"workspace_id": ws_a, "name": "A-only secret rule",
                   "kind": "authority_contains", "spec": {"needles": ["Testing"]}})
        rest("POST", "opportunity_matches", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"workspace_id": ws_a, "opportunity_id": opportunity_id,
                   "state": "excluded", "excluded_by_rule": "A-only secret rule"})
        rest("POST", "opportunity_matches", bearer=SERVICE_KEY, key=SERVICE_KEY,
             body={"workspace_id": ws_b, "opportunity_id": opportunity_id,
                   "state": "in_scope", "eligibility": "likely_eligible",
                   "eligibility_reason": "B's private verdict"})

        yield {"ws_a": ws_a, "ws_b": ws_b, "opportunity_id": opportunity_id}
    finally:
        if opportunity_id:
            rest("DELETE", "opportunities", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 query=f"?id=eq.{opportunity_id}")
        for uid in users:
            admin_delete_user(uid)
        for ws in workspaces:
            rest("DELETE", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY, query=f"?id=eq.{ws}")


def test_both_workspaces_see_the_same_public_corpus_row(two_workspaces_one_corpus):
    """The whole reason for the exception: one crawl serves everyone."""
    ref = two_workspaces_one_corpus["opportunity_id"]
    for email in (EMAIL_A, EMAIL_B):
        token = sign_in(email, PW)
        _, rows = rest("GET", "opportunities", bearer=token, key=ANON_KEY, query=f"?id=eq.{ref}")
        assert len(rows) == 1, f"{email} cannot see the shared corpus"
        assert rows[0]["portal_ref_no"] == "TEST/ISO/2026/1"


def test_neither_workspace_sees_the_others_decisions(two_workspaces_one_corpus):
    """A consultant running two clients must never see client A's shortlist inside B (F-US3)."""
    token_a = sign_in(EMAIL_A, PW)
    _, a_rows = rest("GET", "opportunity_matches", bearer=token_a, key=ANON_KEY, query="?select=*")
    assert len(a_rows) == 1
    assert a_rows[0]["workspace_id"] == two_workspaces_one_corpus["ws_a"]
    assert a_rows[0]["excluded_by_rule"] == "A-only secret rule"

    token_b = sign_in(EMAIL_B, PW)
    _, b_rows = rest("GET", "opportunity_matches", bearer=token_b, key=ANON_KEY, query="?select=*")
    assert len(b_rows) == 1
    assert b_rows[0]["workspace_id"] == two_workspaces_one_corpus["ws_b"]
    assert b_rows[0]["eligibility_reason"] == "B's private verdict"
    # The decisive assertion: B's row set contains nothing of A's.
    assert all(r["excluded_by_rule"] != "A-only secret rule" for r in b_rows)


def test_neither_workspace_sees_the_others_rules(two_workspaces_one_corpus):
    token_b = sign_in(EMAIL_B, PW)
    _, rules = rest("GET", "discovery_rules", bearer=token_b, key=ANON_KEY, query="?select=name")
    assert all(r["name"] != "A-only secret rule" for r in rules)


def test_a_signed_in_user_cannot_write_to_the_shared_corpus(two_workspaces_one_corpus):
    """No INSERT policy exists on `opportunities` — only the service-role ingest writes.

    Without this, one customer could inject rows into every other customer's feed, which is a
    far worse failure than the cross-tenant read the exception was worried about.
    """
    token_a = sign_in(EMAIL_A, PW)
    status, _ = rest("POST", "opportunities", bearer=token_a, key=ANON_KEY,
                     body={"source_id": "hostile", "portal_ref_no": "HOSTILE/1"})
    assert status in (401, 403), f"a signed-in user wrote to the shared corpus (status {status})"


def test_an_exclusion_without_a_named_rule_is_rejected_by_the_database(two_workspaces_one_corpus):
    """G-9 / F-AC6 as a schema constraint, verified against a real Postgres.

    The unit tests prove the rules engine never produces an unnamed exclusion. This proves that
    even a code path that tried could not persist one.
    """
    status, _ = rest("POST", "opportunity_matches", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"workspace_id": two_workspaces_one_corpus["ws_b"],
                           "opportunity_id": two_workspaces_one_corpus["opportunity_id"],
                           "state": "excluded"})
    assert status == 400, "the database accepted an exclusion that named no rule"
