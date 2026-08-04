"""ET-6 for the answer library — the failure mode this feature invents.

Every other table in this product leaks DATA when isolation breaks. This one leaks a client's
own prose into a competitor's proposal: a consultancy running two bidders in the same category
would have client A's winning methodology suggested to client B, and B would submit it. That is
not a privacy incident, it is the end of the business.

The unit suite stubs the database, so it proves the guards and nothing about the scoping. This
file is the only evidence that answers, past bids and style profiles are actually confined —
and it runs against a real database, with real RLS.
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

PW = "Answer-Isolation-Pw-24!"
EMAIL_A = "answer-isolation-a@tendercraft.test"
EMAIL_B = "answer-isolation-b@tendercraft.test"

A_ANSWER = "Client A's winning methodology: a four-phase rollout with embedded UAT."
B_ANSWER = "Client B's own approach: a single-phase cutover with parallel running."

pytestmark = requires_supabase


@pytest.fixture(scope="module")
def two_bidders():
    """Two workspaces, each with one past bid, one mined answer and one style profile."""
    users: list[str] = []
    workspaces: list[str] = []
    try:
        admin_delete_users_by_email(EMAIL_A, EMAIL_B)
        _, wa = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"name": "Answer Workspace A"})
        _, wb = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"name": "Answer Workspace B"})
        ws_a, ws_b = wa[0]["id"], wb[0]["id"]
        workspaces += [ws_a, ws_b]

        uid_a = admin_create_user(EMAIL_A, PW)
        uid_b = admin_create_user(EMAIL_B, PW)
        users += [uid_a, uid_b]
        grant_membership(uid_a, ws_a, email=EMAIL_A)
        grant_membership(uid_b, ws_b, email=EMAIL_B)

        ids = {"ws_a": ws_a, "ws_b": ws_b}
        for side, ws, answer in (("a", ws_a, A_ANSWER), ("b", ws_b, B_ANSWER)):
            _, bid = rest("POST", "past_bids", bearer=SERVICE_KEY, key=SERVICE_KEY,
                          body={"workspace_id": ws, "name": f"Bid {side.upper()}",
                                "authority": "Ministry of Testing", "outcome": "won"})
            _, ans = rest("POST", "answers", bearer=SERVICE_KEY, key=SERVICE_KEY,
                          body={"workspace_id": ws, "past_bid_id": bid[0]["id"],
                                "requirement_text": "implementation methodology",
                                "answer_text": answer, "mined_by": "heading"})
            rest("POST", "style_profiles", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 body={"workspace_id": ws, "brief": f"House style of {side.upper()}",
                       "metrics": {}, "built_from": 1})
            ids[f"answer_{side}"] = ans[0]["id"]
            ids[f"bid_{side}"] = bid[0]["id"]

        yield ids
    finally:
        for uid in users:
            admin_delete_user(uid)
        for ws in workspaces:
            rest("DELETE", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY, query=f"?id=eq.{ws}")


def test_a_bidder_never_sees_another_bidders_answers(two_bidders):
    """The decisive one. B's suggestion pool must not contain a syllable of A's proposal."""
    token_b = sign_in(EMAIL_B, PW)
    _, rows = rest("GET", "answers", bearer=token_b, key=ANON_KEY, query="?select=*")
    assert len(rows) == 1
    assert rows[0]["workspace_id"] == two_bidders["ws_b"]
    assert all(r["answer_text"] != A_ANSWER for r in rows)


def test_reading_another_workspaces_answer_by_id_returns_nothing(two_bidders):
    """Guessing an id must fail too — a filter that only works without one is not isolation."""
    token_b = sign_in(EMAIL_B, PW)
    _, rows = rest("GET", "answers", bearer=token_b, key=ANON_KEY,
                   query=f"?id=eq.{two_bidders['answer_a']}&select=*")
    assert rows == []


def test_past_bids_and_their_outcomes_stay_private(two_bidders):
    """Which tenders a competitor bid on, and whether they won, is commercially sensitive."""
    token_b = sign_in(EMAIL_B, PW)
    _, rows = rest("GET", "past_bids", bearer=token_b, key=ANON_KEY, query="?select=*")
    assert [r["name"] for r in rows] == ["Bid B"]


def test_a_style_profile_is_not_readable_across_workspaces(two_bidders):
    """The brief describes how a firm writes — recognisable, and not B's to have."""
    token_b = sign_in(EMAIL_B, PW)
    _, rows = rest("GET", "style_profiles", bearer=token_b, key=ANON_KEY, query="?select=brief")
    assert [r["brief"] for r in rows] == ["House style of B"]


def test_a_bidder_cannot_write_an_answer_into_another_workspace(two_bidders):
    """RLS's WITH CHECK: forging workspace_id must be refused, not silently accepted."""
    token_b = sign_in(EMAIL_B, PW)
    status, _ = rest(
        "POST", "answers", bearer=token_b, key=ANON_KEY,
        body={"workspace_id": two_bidders["ws_a"], "past_bid_id": two_bidders["bid_a"],
              "requirement_text": "injected", "answer_text": "should never land"},
    )
    assert status in (401, 403), f"cross-workspace answer insert was accepted ({status})"


def test_usage_receipts_do_not_leak_across_workspaces(two_bidders):
    """answer_usages is the G-AC6 audit trail; who reused what is as private as the answer."""
    rest("POST", "answer_usages", bearer=SERVICE_KEY, key=SERVICE_KEY,
         body={"workspace_id": two_bidders["ws_a"], "answer_id": two_bidders["answer_a"],
               "target": "section:approach_methodology"})
    token_b = sign_in(EMAIL_B, PW)
    _, rows = rest("GET", "answer_usages", bearer=token_b, key=ANON_KEY, query="?select=*")
    assert rows == []
