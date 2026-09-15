"""C-FR1/C-FR3/C-FR5 eligibility comparators + gates-not-weights recommendation."""

from datetime import date

import pytest

from app.deterministic.eligibility import (
    CriterionOutcome,
    average_annual_turnover,
    compare_numeric,
    completed_within,
    is_valid_on,
    normalise_fy,
    recent_fys,
    recommend,
)
from app.deterministic.types import Recommendation, RequirementLevel, Verdict

MAND = RequirementLevel.MANDATORY
DES = RequirementLevel.DESIRABLE


# --- compare_numeric ---
@pytest.mark.parametrize(
    "actual,required,op,expected",
    [
        (10.0, 10.0, ">=", True),
        (9.9, 10.0, ">=", False),
        (8.0, 10.0, "<=", True),
        (11.0, 10.0, ">", True),
        (10.0, 10.0, ">", False),
        (9.0, 10.0, "<", True),
        (10.0, 10.0, "==", True),
    ],
)
def test_compare_numeric(actual, required, op, expected):
    assert compare_numeric(actual, required, op) is expected


def test_compare_numeric_rejects_unknown_operator():
    with pytest.raises(ValueError, match="unsupported operator"):
        compare_numeric(1, 2, "≈")


# --- average_annual_turnover (FY normalization) ---
def test_average_turnover_over_three_fys():
    # PRD fixture: ₹6.8 + ₹8.1 + ₹9.7 Cr average = ₹8.2 Cr
    fy = {"FY23": 6.8, "FY24": 8.1, "FY25": 9.7}
    avg = average_annual_turnover(fy, ["FY23", "FY24", "FY25"])
    assert avg == pytest.approx(8.2, abs=0.01)
    assert compare_numeric(avg, 10.0, ">=") is False  # the ₹1.8 Cr gap in the design fixture


def test_average_turnover_missing_fy_returns_none():
    fy = {"FY23": 6.8, "FY25": 9.7}  # FY24 absent
    assert average_annual_turnover(fy, ["FY23", "FY24", "FY25"]) is None


def test_average_turnover_ignores_extra_fys():
    fy = {"FY22": 5.0, "FY23": 6.0, "FY24": 8.0, "FY25": 10.0}
    assert average_annual_turnover(fy, ["FY24", "FY25"]) == pytest.approx(9.0)


def test_average_turnover_empty_required_raises():
    with pytest.raises(ValueError):
        average_annual_turnover({"FY23": 6.8}, [])


def test_average_turnover_dedupes_repeated_fy():
    # a repeated FY must not double-count and skew the average toward a false Pass/Fail
    fy = {"FY24": 8.0, "FY25": 10.0}
    assert average_annual_turnover(fy, ["FY24", "FY25", "FY24"]) == pytest.approx(9.0)


# --- dates ---
def test_valid_on_boundary_is_inclusive():
    assert is_valid_on(date(2026, 8, 14), date(2026, 8, 14)) is True


def test_expired_certificate_is_invalid():
    # design fixture: ISO 9001 expired 03/2026, bid in 08/2026
    assert is_valid_on(date(2026, 3, 31), date(2026, 8, 14)) is False


def test_completed_within_window():
    assert completed_within(date(2024, 11, 1), date(2026, 8, 14), years=5) is True


def test_completed_too_old_is_outside_window():
    assert completed_within(date(2019, 1, 1), date(2026, 8, 14), years=5) is False


def test_completed_in_future_is_outside_window():
    assert completed_within(date(2027, 1, 1), date(2026, 8, 14), years=5) is False


def test_completed_within_rejects_nonpositive_years():
    with pytest.raises(ValueError):
        completed_within(date(2024, 1, 1), date(2026, 1, 1), years=0)


# --- exemption overlay (C-FR3) ---
def test_granted_exemption_waives_a_mandatory_fail():
    o = CriterionOutcome(
        "turnover", MAND, Verdict.FAIL, exemption_granted=True, exemption_clause="4.5"
    )
    assert o.effective_verdict() is Verdict.PASS


def test_exemption_does_not_touch_a_pass():
    o = CriterionOutcome("iso", MAND, Verdict.PASS, exemption_granted=True)
    assert o.effective_verdict() is Verdict.PASS


def test_ungranted_exemption_leaves_fail_intact():
    o = CriterionOutcome("turnover", MAND, Verdict.FAIL, exemption_granted=False)
    assert o.effective_verdict() is Verdict.FAIL


# --- recommend: gates-not-weights (C-FR5) ---
def test_all_mandatory_pass_recommends_bid():
    outcomes = [
        CriterionOutcome("a", MAND, Verdict.PASS),
        CriterionOutcome("b", MAND, Verdict.PASS),
        CriterionOutcome("c", DES, Verdict.FAIL),  # desirable fail does NOT gate
    ]
    assert recommend(outcomes) is Recommendation.BID


def test_single_mandatory_fail_caps_at_no_bid():
    outcomes = [
        CriterionOutcome("a", MAND, Verdict.PASS),
        CriterionOutcome("b", MAND, Verdict.FAIL),
    ]
    assert recommend(outcomes) is Recommendation.NO_BID


def test_mandatory_needs_review_is_conservative_not_bid():
    # ET-1: borderline never auto-passes
    outcomes = [
        CriterionOutcome("a", MAND, Verdict.PASS),
        CriterionOutcome("b", MAND, Verdict.NEEDS_REVIEW),
    ]
    assert recommend(outcomes) is Recommendation.NEEDS_REVIEW


def test_fail_outranks_needs_review():
    outcomes = [
        CriterionOutcome("a", MAND, Verdict.NEEDS_REVIEW),
        CriterionOutcome("b", MAND, Verdict.FAIL),
    ]
    assert recommend(outcomes) is Recommendation.NO_BID


def test_exemption_flips_fail_and_allows_bid():
    # MSE turnover waiver (design fixture): the only mandatory fail is exempt -> Bid
    outcomes = [
        CriterionOutcome(
            "turnover", MAND, Verdict.FAIL, exemption_granted=True, exemption_clause="4.5"
        ),
        CriterionOutcome("experience", MAND, Verdict.PASS),
    ]
    assert recommend(outcomes) is Recommendation.BID


def test_no_mandatory_criteria_is_not_needs_review():
    """It is NO_GATES. Needs-review asks a human to resolve something; a tender stating no
    mandatory eligibility condition has nothing to resolve and disqualifies nobody."""
    assert recommend([CriterionOutcome("a", DES, Verdict.PASS)]) is Recommendation.NO_GATES


def test_desirable_fail_without_mandatory_never_leaks_into_no_bid():
    # only mandatory criteria gate (C-FR5)
    assert recommend([CriterionOutcome("a", DES, Verdict.FAIL)]) is Recommendation.NO_GATES


def test_empty_outcomes_is_no_gates():
    assert recommend([]) is Recommendation.NO_GATES


# ── the financial-year window ────────────────────────────────────────────────────────


def test_a_bid_after_march_counts_back_from_the_year_that_just_closed():
    """A bid on 14 August 2026 sits in FY27, whose year is not over. The last COMPLETED
    financial year ends 31 March 2026 and the profile labels it FY26. Off by one here shifts
    the whole window a year on a hard, non-overridable financial gate."""
    assert recent_fys(date(2026, 8, 14), 3) == ("FY24", "FY25", "FY26")


def test_a_bid_before_april_counts_back_one_further():
    """1 February 2026 is inside FY26, which has not closed either."""
    assert recent_fys(date(2026, 2, 1), 3) == ("FY23", "FY24", "FY25")


def test_the_window_is_oldest_first_and_a_zero_count_is_empty():
    assert recent_fys(date(2026, 8, 14), 1) == ("FY26",)
    assert recent_fys(date(2026, 8, 14), 0) == ()
    assert recent_fys(date(2026, 8, 14), -1) == ()


def test_the_window_wraps_across_a_century():
    assert recent_fys(date(2001, 6, 1), 3) == ("FY99", "FY00", "FY01")


@pytest.mark.parametrize("label,expected", [
    ("2022-23", "FY23"),
    ("F.Y. 2024-25", "FY25"),
    ("FY 24-25", "FY25"),
    ("FY25", "FY25"),
    ("2025", "FY25"),
    ("2024-2025", "FY25"),
])
def test_a_tender_may_write_a_financial_year_any_way_it_likes(label, expected):
    """Indian financial years end on 31 March and are named for the CLOSING year, which is
    what `profile_financials.fy_label` stores."""
    assert normalise_fy(label) == expected


@pytest.mark.parametrize("label", ["", "the last three years", None])
def test_a_label_that_will_not_normalise_is_absent_rather_than_guessed(label):
    """It then drops out of the window, `average_annual_turnover` returns None, and the gate
    reads needs-review — honest by construction."""
    assert normalise_fy(label) is None
