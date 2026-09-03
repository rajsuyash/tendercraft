"""ET-6 for Module H — and the constraints that keep the comparator honest.

A manufacturing envelope is the most commercially sensitive row this product has ever stored.
It is not a document a bidder wrote; it is the exact boundary of what their plant can produce —
which diameters, which grades, which standards. A competitor holding it knows precisely which
tenders to contest and which to concede. It is worth more to a rival than any proposal.

The unit suite stubs the database, so it proves the comparator's arithmetic and nothing about
scoping. This file is the only evidence that envelopes, catalogues, line items and parameters
are actually confined, and it runs against a real database with real RLS.

It also pins two things a unit test cannot reach, both of which are silent when broken:

  * the CHECK constraints — a parameter that is neither a bounded numeric nor a populated enum
    is unreadable, and would surface forever as `unknown` with no error anywhere
  * the PARTIAL unique indexes — Postgres treats NULLs as distinct, so the obvious wide unique
    constraint would accept the same parameter twice and let the comparator read whichever of
    two contradictory values came back first
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

PW = "Catalogue-Isolation-Pw-24!"
EMAIL_A = "catalogue-isolation-a@tendercraft.test"
EMAIL_B = "catalogue-isolation-b@tendercraft.test"

# The envelopes differ in the way that matters commercially: A can make the heavy stuff.
A_ENVELOPE = "A — steel wire rope, 6-60 mm"
B_ENVELOPE = "B — steel wire rope, 6-24 mm"

pytestmark = requires_supabase


@pytest.fixture(scope="module")
def two_manufacturers():
    """Two workspaces, each with an envelope, a listed catalogue item and a tender line item."""
    users: list[str] = []
    workspaces: list[str] = []
    try:
        admin_delete_users_by_email(EMAIL_A, EMAIL_B)
        _, wa = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"name": "Catalogue Workspace A"})
        _, wb = rest("POST", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"name": "Catalogue Workspace B"})
        ws_a, ws_b = wa[0]["id"], wb[0]["id"]
        workspaces += [ws_a, ws_b]

        uid_a = admin_create_user(EMAIL_A, PW)
        uid_b = admin_create_user(EMAIL_B, PW)
        users += [uid_a, uid_b]
        grant_membership(uid_a, ws_a, email=EMAIL_A)
        grant_membership(uid_b, ws_b, email=EMAIL_B)

        ids = {"ws_a": ws_a, "ws_b": ws_b}
        for side, ws, label, top in (("a", ws_a, A_ENVELOPE, 60), ("b", ws_b, B_ENVELOPE, 24)):
            _, env = rest("POST", "product_specs", bearer=SERVICE_KEY, key=SERVICE_KEY,
                          prefer="return=representation",
                          body={"workspace_id": ws, "spec_kind": "envelope", "label": label,
                                "standard_ref": "IS 2266"})
            env_id = env[0]["id"]
            rest("POST", "spec_parameters", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 body={"workspace_id": ws, "product_spec_id": env_id, "param_key": "diameter",
                       "kind": "numeric", "unit": "mm", "num_min": 6, "num_max": top,
                       "raw_text": f"6-{top} mm", "confirmed": True})
            rest("POST", "product_specs", bearer=SERVICE_KEY, key=SERVICE_KEY,
                 body={"workspace_id": ws, "spec_kind": "catalogue",
                       "label": f"{side.upper()}-SKU-4471", "parent_envelope_id": env_id,
                       "gem_catalogue_id": f"GEM-CAT-{side.upper()}-4471"})

            _, tender = rest("POST", "tenders", bearer=SERVICE_KEY, key=SERVICE_KEY,
                             prefer="return=representation",
                             body={"workspace_id": ws, "title": f"Rope tender {side.upper()}"})
            _, line = rest("POST", "tender_line_items", bearer=SERVICE_KEY, key=SERVICE_KEY,
                           prefer="return=representation",
                           body={"workspace_id": ws, "tender_id": tender[0]["id"],
                                 "schedule_ref": "Schedule-A", "item_ref": "1",
                                 "description": f"Wire rope for {side.upper()}",
                                 "quantity": 5000, "uom": "m",
                                 "anchor_document": "BOQ.xlsx", "anchor_row": 14})
            ids[f"envelope_{side}"] = env_id
            ids[f"line_{side}"] = line[0]["id"]
            ids[f"tender_{side}"] = tender[0]["id"]

        yield ids
    finally:
        for uid in users:
            admin_delete_user(uid)
        for ws in workspaces:
            rest("DELETE", "workspaces", bearer=SERVICE_KEY, key=SERVICE_KEY, query=f"?id=eq.{ws}")


# ── the decisive ones ────────────────────────────────────────────────────────

def test_a_manufacturer_never_sees_another_manufacturers_envelope(two_manufacturers):
    """What a rival plant can and cannot produce is the crown jewel. It must not cross."""
    token_b = sign_in(EMAIL_B, PW)
    _, rows = rest("GET", "product_specs", bearer=token_b, key=ANON_KEY,
                   query="?spec_kind=eq.envelope&select=*")
    assert [r["label"] for r in rows] == [B_ENVELOPE]
    assert all(r["workspace_id"] == two_manufacturers["ws_b"] for r in rows)


def test_reading_another_workspaces_envelope_by_id_returns_nothing(two_manufacturers):
    """Guessing an id must fail too — a filter that only works without one is not isolation."""
    token_b = sign_in(EMAIL_B, PW)
    _, rows = rest("GET", "product_specs", bearer=token_b, key=ANON_KEY,
                   query=f"?id=eq.{two_manufacturers['envelope_a']}&select=*")
    assert rows == []


def test_the_parameters_that_carry_the_actual_capability_stay_private(two_manufacturers):
    """The label is a name; the parameters are the secret. Leaking these leaks the envelope."""
    token_b = sign_in(EMAIL_B, PW)
    _, rows = rest("GET", "spec_parameters", bearer=token_b, key=ANON_KEY, query="?select=*")
    assert len(rows) == 1
    assert rows[0]["workspace_id"] == two_manufacturers["ws_b"]
    # B tops out at 24 mm. Seeing 60 would mean seeing A's plant.
    assert float(rows[0]["num_max"]) == 24.0


def test_a_gem_catalogue_id_is_not_readable_across_workspaces(two_manufacturers):
    """Which SKUs a competitor has already listed is their bidding position, pre-announced."""
    token_b = sign_in(EMAIL_B, PW)
    _, rows = rest("GET", "product_specs", bearer=token_b, key=ANON_KEY,
                   query="?spec_kind=eq.catalogue&select=gem_catalogue_id")
    assert [r["gem_catalogue_id"] for r in rows] == ["GEM-CAT-B-4471"]


def test_tender_line_items_stay_with_their_workspace(two_manufacturers):
    """A schedule is read off a public notice, but WHICH lines a bidder shredded is not public."""
    token_b = sign_in(EMAIL_B, PW)
    _, rows = rest("GET", "tender_line_items", bearer=token_b, key=ANON_KEY, query="?select=*")
    assert [r["description"] for r in rows] == ["Wire rope for B"]


def test_a_workspace_cannot_write_a_spec_into_another_workspace(two_manufacturers):
    """RLS `with check` — reading is half of isolation; the other half is not being able to
    plant a row in someone else's plant profile."""
    token_b = sign_in(EMAIL_B, PW)
    status, _ = rest("POST", "product_specs", bearer=token_b, key=ANON_KEY,
                     body={"workspace_id": two_manufacturers["ws_a"], "spec_kind": "envelope",
                           "label": "planted by B"})
    assert status >= 400


# ── the constraints, against a real database ─────────────────────────────────

def test_a_parameter_must_belong_to_exactly_one_side(two_manufacturers):
    """Both owners set, or neither. A row claiming to be capability AND requirement is the one
    thing the comparator reads them to tell apart."""
    ws_b = two_manufacturers["ws_b"]
    base = {"workspace_id": ws_b, "param_key": "orphan", "kind": "numeric", "num_min": 1}
    status_neither, _ = rest("POST", "spec_parameters", bearer=SERVICE_KEY, key=SERVICE_KEY,
                             body=base)
    assert status_neither >= 400
    status_both, _ = rest("POST", "spec_parameters", bearer=SERVICE_KEY, key=SERVICE_KEY,
                          body={**base, "product_spec_id": two_manufacturers["envelope_b"],
                                "line_item_id": two_manufacturers["line_b"]})
    assert status_both >= 400


@pytest.mark.parametrize("bad,reason", [
    ({"kind": "numeric"}, "a numeric with no bound is unreadable"),
    ({"kind": "numeric", "num_min": 60, "num_max": 6}, "an inverted range matches nothing"),
    ({"kind": "enum"}, "an enum with no allowed values can never match"),
])
def test_an_unreadable_parameter_is_refused_at_write_time(two_manufacturers, bad, reason):
    """Each of these would be accepted silently by a jsonb column and then report `unknown`
    forever — the failure mode that reads as "the feature does not work"."""
    status, _ = rest("POST", "spec_parameters", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"workspace_id": two_manufacturers["ws_b"],
                           "line_item_id": two_manufacturers["line_b"],
                           "param_key": "bad", "raw_text": reason, **bad})
    assert status >= 400, reason


def test_the_same_parameter_cannot_be_stored_twice_for_one_line_item(two_manufacturers):
    """The NULL-distinctness trap. `unique (workspace_id, product_spec_id, line_item_id, key)`
    would accept this pair happily, because product_spec_id is NULL on both rows and Postgres
    treats NULLs as distinct — leaving the comparator to pick one of two contradictory values
    by row order. The partial indexes are what make this fail."""
    body = {"workspace_id": two_manufacturers["ws_b"],
            "line_item_id": two_manufacturers["line_b"],
            "param_key": "tensile_grade", "kind": "enum",
            "allowed_values": ["1770"], "raw_text": "1770 N/mm2"}
    first, _ = rest("POST", "spec_parameters", bearer=SERVICE_KEY, key=SERVICE_KEY, body=body)
    assert first < 400
    second, _ = rest("POST", "spec_parameters", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={**body, "allowed_values": ["1960"], "raw_text": "1960 N/mm2"})
    assert second >= 400


def test_re_ingesting_the_same_boq_row_does_not_duplicate_a_line_item(two_manufacturers):
    """A package re-uploaded after a corrigendum must update its schedule, not double it —
    two rows for one BOQ line means every count on the fit screen is wrong."""
    status, _ = rest("POST", "tender_line_items", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"workspace_id": two_manufacturers["ws_b"],
                           "tender_id": two_manufacturers["tender_b"],
                           "description": "Wire rope for B, re-read",
                           "anchor_document": "BOQ.xlsx", "anchor_row": 14})
    assert status >= 400


def test_an_envelope_cannot_claim_a_parent(two_manufacturers):
    """parent_envelope_id records which envelope a CATALOGUE item was created from. An envelope
    with a parent is a cycle waiting to happen and means nothing."""
    status, _ = rest("POST", "product_specs", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body={"workspace_id": two_manufacturers["ws_b"], "spec_kind": "envelope",
                           "label": "envelope with a parent",
                           "parent_envelope_id": two_manufacturers["envelope_b"]})
    assert status >= 400


# ── pre-bid clarifications (migration 0038, UML ask 2) ───────────────────────

def _clarification(ws: str, tender: str, **over) -> dict:
    row = {
        "workspace_id": ws, "tender_id": tender, "param_key": "diameter",
        "kind": "relaxation", "query_text": "Is the stated diameter mandatory?",
        "required_display": "20 mm",
        # This column holds the comparator's reason, which names the plant's own range. It is
        # the reason these rows are as sensitive as the envelope they were derived from.
        "rationale": "required 20 mm is outside 6-24 mm",
    }
    row.update(over)
    return row


def test_a_clarification_never_crosses_workspaces(two_manufacturers):
    """A pre-bid question names which requirement a bidder cannot meet — a rival reading it
    learns where the plant stops and which tender to contest."""
    rest("POST", "tender_clarifications", bearer=SERVICE_KEY, key=SERVICE_KEY,
         body=_clarification(two_manufacturers["ws_a"], two_manufacturers["tender_a"],
                             query_text="A's question"))

    token_b = sign_in(EMAIL_B, PW)
    _, rows = rest("GET", "tender_clarifications", bearer=token_b, key=ANON_KEY, query="?select=*")

    assert all(r["workspace_id"] == two_manufacturers["ws_b"] for r in rows)
    assert "A's question" not in [r["query_text"] for r in rows]


def test_the_rationale_that_names_the_plant_stays_private(two_manufacturers):
    """`rationale` is workspace-internal by design — it is never rendered into query text
    because GeM publishes a buyer's answers to every bidder. RLS is what makes that hold for
    the stored row as well as the sent one."""
    token_b = sign_in(EMAIL_B, PW)
    _, rows = rest("GET", "tender_clarifications", bearer=token_b, key=ANON_KEY,
                   query=f"?tender_id=eq.{two_manufacturers['tender_a']}&select=rationale")

    assert rows == []


def test_a_workspace_cannot_plant_a_clarification_in_another(two_manufacturers):
    token_b = sign_in(EMAIL_B, PW)
    status, _ = rest("POST", "tender_clarifications", bearer=token_b, key=ANON_KEY,
                     body=_clarification(two_manufacturers["ws_a"],
                                         two_manufacturers["tender_a"]))
    assert status >= 400


def test_one_question_per_parameter_per_tender(two_manufacturers):
    """The pack folds by parameter: one diameter deviating across nine schedule lines is one
    question. A second row would make the screen ask the buyer twice."""
    body = _clarification(two_manufacturers["ws_b"], two_manufacturers["tender_b"])
    first, _ = rest("POST", "tender_clarifications", bearer=SERVICE_KEY, key=SERVICE_KEY,
                    body=body)
    assert first < 400
    duplicate, _ = rest("POST", "tender_clarifications", bearer=SERVICE_KEY, key=SERVICE_KEY,
                        body=body)
    assert duplicate >= 400


def test_a_sent_question_cannot_have_its_text_rewritten(two_manufacturers):
    """The trigger, against a real database. Re-deriving the pack after a corrigendum must not
    rewrite the record of what was actually put in front of a public buyer — and the only
    writer that reaches this table is the service role, which bypasses everything else."""
    _, created = rest("POST", "tender_clarifications", bearer=SERVICE_KEY, key=SERVICE_KEY,
                      prefer="return=representation",
                      body=_clarification(two_manufacturers["ws_b"],
                                          two_manufacturers["tender_b"],
                                          param_key="min_breaking_load",
                                          query_text="the words that went to the buyer",
                                          status="sent", sent_at="2026-09-01T00:00:00Z"))
    row_id = created[0]["id"]

    status, _ = rest("PATCH", "tender_clarifications", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     query=f"?id=eq.{row_id}", body={"query_text": "quietly different words"})
    assert status >= 400

    # An ANSWER on the same row is the write this table exists for, and must still go through.
    ok_status, _ = rest("PATCH", "tender_clarifications", bearer=SERVICE_KEY, key=SERVICE_KEY,
                        query=f"?id=eq.{row_id}",
                        body={"status": "answered", "answer_text": "Yes, it is mandatory.",
                              "answer_source": "portal", "answered_at": "2026-09-02T00:00:00Z"})
    assert ok_status < 400


def test_an_answered_status_requires_the_reply_text(two_manufacturers):
    """A status is a claim about something that happened. 'Answered' with no answer is a claim
    about a public buyer that nothing supports."""
    status, _ = rest("POST", "tender_clarifications", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body=_clarification(two_manufacturers["ws_b"],
                                         two_manufacturers["tender_b"],
                                         param_key="tensile_grade", status="answered",
                                         sent_at="2026-09-01T00:00:00Z",
                                         answered_at="2026-09-02T00:00:00Z"))
    assert status >= 400


def test_an_answer_must_say_where_it_came_from(two_manufacturers):
    """An answer with no stated source is an unattributed claim about what a buyer said."""
    status, _ = rest("POST", "tender_clarifications", bearer=SERVICE_KEY, key=SERVICE_KEY,
                     body=_clarification(two_manufacturers["ws_b"],
                                         two_manufacturers["tender_b"],
                                         param_key="core_type",
                                         answer_text="Yes."))
    assert status >= 400
