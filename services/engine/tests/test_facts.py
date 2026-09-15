"""Deciding a gate from facts the bidder actually has on file.

One rule generates most of this file: **a missing fact is needs-review, never a failure.**
A false "you do not qualify" costs the customer a bid they would have won, and nobody audits
the bids they were told to skip, so that error is invisible by construction.

The other half is the shape of the inputs. `Requirement` is what the MODEL may say and
carries no verdict, no actual value and no evidence ids; `ProfileFacts` is what the bidder
has and the model never sees it.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.deterministic.facts import (
    CertRecord,
    ExperienceRecord,
    ProfileFacts,
    Requirement,
    decide_requirement,
    exemption_granted,
    profile_facts,
)
from app.deterministic.types import CheckType, Verdict

BID = date(2026, 8, 14)

FACTS = ProfileFacts(
    fy_turnover_cr={"FY24": 6.8, "FY25": 8.1, "FY26": 9.7},
    net_worth_cr=4.0,
    working_capital_cr=1.5,
    udyam_registration="UDYAM-JH-01-0001",
    gst="20AAACU1234F1Z5",
)


def req(**kw) -> Requirement:
    kw.setdefault("confidence", 0.9)
    return Requirement(**kw)


def turnover(**kw) -> Requirement:
    kw.setdefault("threshold_cr", 10)
    return req(check=CheckType.TURNOVER_AVG, operator=">=", **kw)


# --- the guards that run before any check ------------------------------------------------------


def test_a_requirement_with_no_checkable_condition_asks_rather_than_decides():
    out = decide_requirement(req(check=CheckType.NONE, raw_text="Acceptance to GeM GTC"), FACTS)
    assert out.verdict is Verdict.NEEDS_REVIEW
    assert "no checkable condition" in out.rationale


def test_an_empty_requirement_still_produces_a_sentence():
    assert decide_requirement(req(check=CheckType.NONE), FACTS).rationale == "nothing to check"


def test_a_low_confidence_reading_decides_nothing_on_any_branch():
    """The old code applied this guard to the fuzzy branch only. The numeric branch skipped
    it, which is how confidence 0.01 with no evidence produced a hard PASS."""
    for check in (CheckType.TURNOVER_AVG, CheckType.NET_WORTH, CheckType.EXPERIENCE_COUNT,
                  CheckType.CERTIFICATION_VALID, CheckType.REGISTRATION_PRESENT):
        out = decide_requirement(
            Requirement(check=check, threshold_cr=0.01, min_count=0, confidence=0.74),
            FACTS, BID, ("FY24",),
        )
        assert out.verdict is Verdict.NEEDS_REVIEW, check
        assert "low confidence" in out.rationale


def test_exactly_the_matcher_threshold_is_allowed_through():
    """0.75 is the PRD's router threshold (C-AC5), not 0.76."""
    out = decide_requirement(turnover(confidence=0.75), FACTS, BID, ("FY24", "FY25", "FY26"))
    assert out.verdict is Verdict.FAIL


# --- turnover ----------------------------------------------------------------------------------


def test_the_average_is_computed_over_the_window_the_tender_named():
    out = decide_requirement(turnover(), FACTS, BID, ("FY24", "FY25", "FY26"))
    assert out.verdict is Verdict.FAIL
    assert out.actual_display == "₹8.20 Cr (avg FY24|FY25|FY26)"
    assert out.required_display == "₹10.00 Cr"
    assert out.gap_note.endswith("gap ₹1.80 Cr")
    assert out.fy_window == ("FY24", "FY25", "FY26")


def test_a_met_threshold_passes_and_carries_no_gap():
    out = decide_requirement(turnover(threshold_cr=8), FACTS, BID, ("FY24", "FY25", "FY26"))
    assert out.verdict is Verdict.PASS
    assert out.gap_note == ""


def test_the_window_falls_back_to_the_labels_on_the_requirement():
    out = decide_requirement(turnover(threshold_cr=7, fy_labels=("FY24", "FY25")), FACTS, BID)
    assert out.verdict is Verdict.PASS
    assert out.fy_window == ("FY24", "FY25")


def test_no_window_at_all_is_needs_review_not_an_average_of_whatever_is_on_file():
    """Averaging the years the BIDDER happens to have and calling it the answer is the exact
    defect `sections.py::assemble_compliance_pq` was rewritten to kill — on a hard,
    non-overridable financial gate."""
    out = decide_requirement(turnover(), FACTS, BID)
    assert out.verdict is Verdict.NEEDS_REVIEW
    assert "which financial years" in out.rationale


def test_a_missing_financial_year_names_itself_and_fails_nothing():
    out = decide_requirement(turnover(), FACTS, BID, ("FY22", "FY23", "FY24"))
    assert out.verdict is Verdict.NEEDS_REVIEW
    assert out.missing_facts == ("profile_financials:FY22", "profile_financials:FY23")


def test_a_tender_stating_no_threshold_cannot_be_compared_against():
    out = decide_requirement(
        req(check=CheckType.TURNOVER_AVG), FACTS, BID, ("FY24", "FY25", "FY26"))
    assert out.verdict is Verdict.NEEDS_REVIEW
    assert "no threshold" in out.rationale


# --- net worth and working capital -------------------------------------------------------------


def test_net_worth_uses_the_profile_column():
    out = decide_requirement(req(check=CheckType.NET_WORTH, threshold_cr=2.0), FACTS)
    assert out.verdict is Verdict.PASS
    assert out.operator == ">="  # the default when the clause states no comparator
    assert out.actual_display == "₹4.00 Cr"


def test_working_capital_can_be_required_to_stay_under_a_ceiling():
    out = decide_requirement(
        req(check=CheckType.WORKING_CAPITAL, operator="<=", threshold_cr=1.0), FACTS)
    assert out.verdict is Verdict.FAIL
    assert out.operator == "<="


def test_a_figure_not_on_file_is_needs_review_and_names_the_column():
    out = decide_requirement(req(check=CheckType.NET_WORTH, threshold_cr=2.0), ProfileFacts())
    assert out.verdict is Verdict.NEEDS_REVIEW
    assert out.missing_facts == ("vendor_profiles.net_worth_cr",)


# --- experience --------------------------------------------------------------------------------


def _exp(i, value, when):
    return ExperienceRecord(i, value, when)


THREE_WORKS = ProfileFacts(experience=(
    _exp("e1", 4.0, date(2024, 11, 1)),
    _exp("e2", 3.0, date(2023, 6, 1)),
    _exp("e3", 0.5, date(2019, 1, 1)),
))


def test_enough_qualifying_works_passes_and_cites_them():
    out = decide_requirement(
        req(check=CheckType.EXPERIENCE_COUNT, min_count=2, threshold_cr=1.0, years_window=5),
        THREE_WORKS, BID)
    assert out.verdict is Verdict.PASS
    assert out.evidence_ids == ("e1", "e2")


def test_a_work_outside_the_window_or_under_the_value_does_not_count():
    out = decide_requirement(
        req(check=CheckType.EXPERIENCE_COUNT, min_count=3, threshold_cr=1.0, years_window=5),
        THREE_WORKS, BID)
    assert out.verdict is Verdict.FAIL
    assert out.actual_display == "2 qualifying"
    assert out.gap_note == "1 more qualifying work(s) needed"


def test_with_no_window_and_no_value_test_every_dated_record_counts():
    out = decide_requirement(
        req(check=CheckType.EXPERIENCE_COUNT, min_count=3), THREE_WORKS, BID)
    assert out.verdict is Verdict.PASS


def test_an_incomplete_record_makes_the_count_unproven_not_short():
    """A bidder with ten qualifying projects and one undated row must never read as a
    failure."""
    facts = ProfileFacts(experience=(_exp("e1", 4.0, date(2024, 1, 1)), _exp("e2", None, None)))
    out = decide_requirement(req(check=CheckType.EXPERIENCE_COUNT, min_count=2), facts, BID)
    assert out.verdict is Verdict.NEEDS_REVIEW
    assert out.missing_facts == ("experience_records:e2",)


def test_a_tender_stating_no_count_cannot_be_counted_against():
    out = decide_requirement(req(check=CheckType.EXPERIENCE_COUNT), THREE_WORKS, BID)
    assert out.verdict is Verdict.NEEDS_REVIEW
    assert "no number of works" in out.rationale


def test_a_lookback_window_without_a_submission_date_is_unresolvable():
    out = decide_requirement(
        req(check=CheckType.EXPERIENCE_COUNT, min_count=1, years_window=5), THREE_WORKS, None)
    assert out.verdict is Verdict.NEEDS_REVIEW
    assert out.missing_facts == ("tenders.deadline",)


# --- certifications ----------------------------------------------------------------------------


CERTS = ProfileFacts(certifications=(
    CertRecord("c1", "ISO 9001:2015", date(2027, 3, 31)),
    CertRecord("c2", "API Spec 9A", date(2024, 1, 1)),
))


def test_a_certification_valid_on_the_submission_date_passes():
    out = decide_requirement(
        req(check=CheckType.CERTIFICATION_VALID, certification_name="ISO 9001"), CERTS, BID)
    assert out.verdict is Verdict.PASS
    assert out.evidence_ids == ("c1",)
    assert out.actual_display == "ISO 9001:2015 valid to 2027-03-31"


def test_a_certification_that_had_expired_by_the_submission_date_fails():
    out = decide_requirement(
        req(check=CheckType.CERTIFICATION_VALID, certification_name="API Spec 9A"), CERTS, BID)
    assert out.verdict is Verdict.FAIL
    assert out.gap_note == "renew API Spec 9A — expired 2024-01-01"


def test_a_certification_not_on_file_is_not_a_certification_the_bidder_lacks():
    """The same three-state rule the PQ sheet learned when it printed EXPIRED against four
    current ISO and API certificates."""
    out = decide_requirement(
        req(check=CheckType.CERTIFICATION_VALID, certification_name="BIS"), CERTS, BID)
    assert out.verdict is Verdict.NEEDS_REVIEW
    assert out.missing_facts == ("certifications",)


def test_a_certification_with_no_expiry_recorded_cannot_be_dated():
    facts = ProfileFacts(certifications=(CertRecord("c9", "ISO 9001", None),))
    out = decide_requirement(
        req(check=CheckType.CERTIFICATION_VALID, certification_name="ISO 9001"), facts, BID)
    assert out.verdict is Verdict.NEEDS_REVIEW
    assert out.missing_facts == ("certifications:c9",)


def test_validity_cannot_be_checked_without_a_submission_date():
    out = decide_requirement(
        req(check=CheckType.CERTIFICATION_VALID, certification_name="ISO 9001"), CERTS, None)
    assert out.verdict is Verdict.NEEDS_REVIEW
    assert out.missing_facts == ("tenders.deadline",)


def test_a_tender_that_names_no_certification_asks_rather_than_guesses():
    out = decide_requirement(req(check=CheckType.CERTIFICATION_VALID), CERTS, BID)
    assert out.verdict is Verdict.NEEDS_REVIEW
    assert "does not name" in out.rationale


# --- registrations -----------------------------------------------------------------------------


def test_a_recorded_registration_passes():
    out = decide_requirement(
        req(check=CheckType.REGISTRATION_PRESENT, registration_key="gst"), FACTS)
    assert out.verdict is Verdict.PASS
    assert out.actual_display == "on file"


@pytest.mark.parametrize("key", ["dpiit", "startup", "pan", "cin", "udyam", "mse"])
def test_an_absent_registration_can_never_fail(key):
    """`dpiit_registered` is `boolean not null default false` and the text fields default to
    empty, so an absent value cannot be told apart from a question nobody has been asked.
    Treating it as a proven negative would produce a NO-BID from a field the bidder has never
    seen."""
    out = decide_requirement(
        req(check=CheckType.REGISTRATION_PRESENT, registration_key=key), ProfileFacts())
    assert out.verdict is Verdict.NEEDS_REVIEW


def test_a_registration_this_profile_does_not_record_is_named_as_such():
    out = decide_requirement(
        req(check=CheckType.REGISTRATION_PRESENT, registration_key="make_in_india"), FACTS)
    assert out.verdict is Verdict.NEEDS_REVIEW
    assert "not a registration this profile records" in out.rationale


def test_a_registration_check_with_no_key_at_all_still_answers():
    out = decide_requirement(req(check=CheckType.REGISTRATION_PRESENT), FACTS)
    assert out.verdict is Verdict.NEEDS_REVIEW


# --- exemptions --------------------------------------------------------------------------------


MSE_EXEMPTION = dict(exemption_for=("mse",), exemption_clause="Cl. 4.5 — MSE relaxation")


def test_an_exemption_is_granted_only_where_the_bidder_is_in_the_class():
    assert exemption_granted(req(**MSE_EXEMPTION), FACTS, Verdict.FAIL) is True
    assert exemption_granted(req(**MSE_EXEMPTION), ProfileFacts(), Verdict.FAIL) is False


@pytest.mark.parametrize("verdict", [Verdict.PASS, Verdict.NEEDS_REVIEW])
def test_there_is_nothing_to_waive_unless_the_gate_failed(verdict):
    assert exemption_granted(req(**MSE_EXEMPTION), FACTS, verdict) is False


def test_an_exemption_without_a_quoted_clause_is_not_an_exemption():
    """The old version was a single model boolean, so one `true` on a mandatory criterion
    flipped NO-BID to BID with nothing resolved anywhere."""
    assert exemption_granted(
        req(exemption_for=("mse",)), FACTS, Verdict.FAIL) is False
    assert exemption_granted(
        req(exemption_clause="Cl. 4.5"), FACTS, Verdict.FAIL) is False


def test_an_exemption_class_no_profile_field_can_prove_is_refused():
    """`make_in_india` is deliberately unmapped: no profile field records it, so an MII
    relaxation can never be resolved and says so rather than guessing."""
    assert exemption_granted(
        req(exemption_for=("make_in_india",), exemption_clause="Cl. 9"),
        FACTS, Verdict.FAIL) is False


def test_a_dpiit_start_up_is_proved_by_the_boolean_column():
    facts = ProfileFacts(dpiit_registered=True)
    assert exemption_granted(
        req(exemption_for=("startup",), exemption_clause="Cl. 4.6"),
        facts, Verdict.FAIL) is True


# --- adapting the stored profile ---------------------------------------------------------------


def test_an_empty_profile_adapts_to_empty_facts_rather_than_raising():
    """The state that must produce "unknown" everywhere, not "fails" anywhere."""
    f = profile_facts({})
    assert f.fy_turnover_cr == {}
    assert f.net_worth_cr is None
    assert f.dpiit_registered is False
    assert f.experience == () and f.certifications == ()


def test_a_full_profile_types_every_field():
    f = profile_facts({
        "legal_identity": {"net_worth_cr": "4.0", "working_capital_cr": 1.5,
                           "udyam_registration": "U-1", "dpiit_registered": True,
                           "gst": "G", "pan": "P", "cin": "C"},
        "financials": [{"fy_label": "FY25", "turnover_cr": "8.1"}],
        "experience_records": [{"id": "e1", "value_cr": 4, "completion_date": "2024-11-01"}],
        "certifications": [{"id": "c1", "name": "ISO 9001", "valid_to": "2027-03-31"}],
    })
    assert f.fy_turnover_cr == {"FY25": 8.1}
    assert f.net_worth_cr == 4.0 and f.working_capital_cr == 1.5
    assert f.dpiit_registered is True
    assert f.pan == "P" and f.cin == "C" and f.gst == "G"
    assert f.experience[0].completion_date == date(2024, 11, 1)
    assert f.certifications[0].valid_to == date(2027, 3, 31)


def test_a_half_written_financial_row_is_dropped_rather_than_read_as_zero():
    """A missing turnover read as 0.0 would drag an average down and manufacture a shortfall
    the bidder does not have."""
    f = profile_facts({"financials": [
        {"fy_label": "FY25", "turnover_cr": None},
        {"fy_label": None, "turnover_cr": 8.1},
        {"fy_label": "FY26", "turnover_cr": 9.7},
    ]})
    assert f.fy_turnover_cr == {"FY26": 9.7}


def test_an_unparseable_number_or_date_is_absent_not_a_crash():
    f = profile_facts({
        "legal_identity": {"net_worth_cr": "not a number"},
        "experience_records": [{"id": "e1", "value_cr": "x", "completion_date": "31/03/2024"}],
        "certifications": [{"id": "c1", "name": "ISO", "valid_to": ""}],
    })
    assert f.net_worth_cr is None
    assert f.experience[0].value_cr is None
    assert f.experience[0].completion_date is None
    assert f.certifications[0].valid_to is None
