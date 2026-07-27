"""The disclosure gate (F28).

This is the only path in either product where evaluation data is packaged for someone outside
the authority, and it cannot be taken back once sent. So the tests are written from the point
of view of the person who should never receive the data: a losing bidder's lawyer reading a
regret letter and looking for a competitor's technical evaluation in it.
"""

import pytest

from evaluate.deterministic.disclosure import (
    FORBIDDEN_FIELDS,
    PERMITTED_FIELDS,
    DisclosureError,
    Outcome,
    assert_disclosable,
    contains_forbidden,
    filter_for_recipient,
    outcome_for,
)

FULL = {
    "tender_title": "City Surveillance and Command Centre",
    "bidder_name": "Arcadia Systems Ltd",
    "own_rank": 3,
    "own_technical_score": "61.5",
    "winner_name": "Kaveri Networks Pvt Ltd",
    "accepted_price_inr": "70600000",
    # everything below must be refused
    "per_member_marks": [{"evaluator": "S. Rao", "mark": 7}],
    "other_bids": [{"bidder": "Sahyadri Civic", "score": 74}],
    "other_prices": {"Sahyadri Civic": "61500000"},
    "consensus_notes": "committee felt the DR plan was thin",
    "coi_declarations": [{"member": "S. Rao", "interest": "none"}],
}


# ── the allowlist ──────────────────────────────────────────────────────────────
def test_only_permitted_fields_survive():
    out = filter_for_recipient(FULL)
    assert set(out.fields) <= set(PERMITTED_FIELDS)
    assert "per_member_marks" not in out.fields
    assert "other_bids" not in out.fields
    assert "other_prices" not in out.fields
    assert "consensus_notes" not in out.fields
    assert "coi_declarations" not in out.fields


def test_the_recipients_own_data_and_the_public_facts_do_survive():
    out = filter_for_recipient(FULL)
    assert out.fields["bidder_name"] == "Arcadia Systems Ltd"
    assert out.fields["own_rank"] == 3
    assert out.fields["winner_name"] == "Kaveri Networks Pvt Ltd"
    assert out.fields["accepted_price_inr"] == "70600000"


def test_refusals_are_reported_not_swallowed():
    """A growing refusal list is the signal that someone upstream is passing more than they
    should. Silently dropping it hides that."""
    out = filter_for_recipient(FULL)
    assert "per_member_marks" in out.refused
    assert "other_prices" in out.refused


def test_an_unknown_field_is_denied_by_default():
    """The whole point of an allowlist. A field nobody anticipated must not ride along."""
    out = filter_for_recipient({**FULL, "some_new_internal_field": "secret"})
    assert "some_new_internal_field" not in out.fields
    assert "some_new_internal_field" in out.refused


def test_the_two_lists_never_overlap():
    """A field cannot be both disclosable and forbidden. If this fails someone edited one list
    without reading the other."""
    assert not set(PERMITTED_FIELDS) & set(FORBIDDEN_FIELDS)


def test_an_empty_payload_produces_nothing_rather_than_erroring():
    out = filter_for_recipient({})
    assert out.fields == {} and out.refused == ()


# ── state gate ─────────────────────────────────────────────────────────────────
def test_nothing_is_disclosable_before_the_ranking_is_final():
    with pytest.raises(DisclosureError, match="not final"):
        assert_disclosable(ranking_final=False, tender_state="active")


def test_nothing_is_disclosable_from_an_archived_tender():
    with pytest.raises(DisclosureError, match="archived"):
        assert_disclosable(ranking_final=True, tender_state="archived")


def test_a_final_active_tender_is_disclosable():
    """Returns rather than raising — the gate is a guard clause, not a predicate."""
    assert assert_disclosable(ranking_final=True, tender_state="active") is None


# ── outcome ────────────────────────────────────────────────────────────────────
def test_rank_one_qualified_is_the_award():
    assert outcome_for(1, True) is Outcome.AWARD


@pytest.mark.parametrize("rank,qualified", [(2, True), (1, False), (None, True), (None, False)])
def test_everything_else_is_a_regret(rank, qualified):
    """Notably rank 1 but NOT qualified: leading on technical score without meeting the
    qualifying mark is not an award, and telling that bidder they won would be a retraction."""
    assert outcome_for(rank, qualified) is Outcome.REGRET


# ── the belt-and-braces check on produced prose ────────────────────────────────
def test_forbidden_values_are_detected_in_generated_text():
    """F28-AC2 is asserted on the produced bytes, not on our intentions."""
    text = "Your bid ranked below that of Sahyadri Civic Infra, which scored 74."
    assert contains_forbidden(text, ["Sahyadri Civic Infra", "Kaveri Networks"]) == \
        ("Sahyadri Civic Infra",)


def test_clean_text_reports_nothing():
    text = "Your bid was ranked third of five. The contract was awarded to Kaveri Networks."
    assert contains_forbidden(text, ["Sahyadri Civic Infra"]) == ()


def test_detection_is_case_insensitive_and_ignores_empty_values():
    assert contains_forbidden("we prefer ARCADIA systems", ["Arcadia Systems", ""]) == \
        ("Arcadia Systems",)
