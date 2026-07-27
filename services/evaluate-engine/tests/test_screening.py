from evaluate.deterministic.screening import (
    auto_non_responsive,
    evaluate_criterion,
    screen_bid,
)
from evaluate.deterministic.types import CompareKind, Criterion, Response, Verdict


def crit(**kw):
    base = dict(id="c1", kind="pq", text="t", compare_kind=CompareKind.NUMERIC,
                compare_op=">=", compare_value="10")
    return Criterion(**{**base, **kw})


class TestNumeric:
    def test_meets(self):
        assert evaluate_criterion(crit(), Response("c1", "12")).verdict is Verdict.MEETS

    def test_fails(self):
        assert evaluate_criterion(crit(), Response("c1", "8")).verdict is Verdict.FAILS

    def test_boundary_is_inclusive(self):
        assert evaluate_criterion(crit(), Response("c1", "10")).verdict is Verdict.MEETS

    def test_commas_are_tolerated(self):
        assert evaluate_criterion(crit(compare_value="1000000"),
                                  Response("c1", "1,200,000")).verdict is Verdict.MEETS

    def test_unparseable_is_not_stated_not_a_fail(self):
        # THE important one: an extraction miss must never disqualify a bidder.
        assert evaluate_criterion(crit(), Response("c1", "see annexure")).verdict is Verdict.NOT_STATED

    def test_equals_operator(self):
        # `=` on a numeric was reachable in production and untested — the exact shape of gap
        # that lets a comparison operator silently change behaviour.
        c = crit(compare_op="=", compare_value="5")
        assert evaluate_criterion(c, Response("c1", "5")).verdict is Verdict.MEETS
        assert evaluate_criterion(c, Response("c1", "6")).verdict is Verdict.FAILS

    def test_lte_operator(self):
        assert evaluate_criterion(crit(compare_op="<=", compare_value="10"),
                                  Response("c1", "9")).verdict is Verdict.MEETS


class TestDate:
    def test_valid_on_date(self):
        c = crit(compare_kind=CompareKind.DATE, compare_op=">=", compare_value="2026-01-01")
        assert evaluate_criterion(c, Response("c1", "2026-06-01")).verdict is Verdict.MEETS

    def test_expired(self):
        c = crit(compare_kind=CompareKind.DATE, compare_op=">=", compare_value="2026-01-01")
        assert evaluate_criterion(c, Response("c1", "2025-06-01")).verdict is Verdict.FAILS

    def test_garbage_date_is_not_stated(self):
        c = crit(compare_kind=CompareKind.DATE, compare_op=">=", compare_value="2026-01-01")
        assert evaluate_criterion(c, Response("c1", "n/a")).verdict is Verdict.NOT_STATED


class TestBoolean:
    def test_present(self):
        c = crit(compare_kind=CompareKind.BOOLEAN, compare_op="=", compare_value="yes")
        assert evaluate_criterion(c, Response("c1", "Yes")).verdict is Verdict.MEETS

    def test_absent(self):
        c = crit(compare_kind=CompareKind.BOOLEAN, compare_op="=", compare_value="yes")
        assert evaluate_criterion(c, Response("c1", "no")).verdict is Verdict.FAILS

    def test_unrecognised_is_not_stated(self):
        c = crit(compare_kind=CompareKind.BOOLEAN, compare_op="=", compare_value="yes")
        assert evaluate_criterion(c, Response("c1", "partially")).verdict is Verdict.NOT_STATED

    def test_missing_required_defaults_to_expecting_true(self):
        c = crit(compare_kind=CompareKind.BOOLEAN, compare_op="=", compare_value=None)
        assert evaluate_criterion(c, Response("c1", "yes")).verdict is Verdict.MEETS


class TestQualitativeAndMissing:
    def test_qualitative_always_routes_to_a_human(self):
        c = crit(compare_kind=CompareKind.QUALITATIVE)
        assert evaluate_criterion(c, Response("c1", "anything")).verdict is Verdict.MANUAL

    def test_no_response_row_at_all(self):
        assert evaluate_criterion(crit(), None).verdict is Verdict.NOT_STATED

    def test_empty_string(self):
        assert evaluate_criterion(crit(), Response("c1", "   ")).verdict is Verdict.NOT_STATED

    def test_missing_required_value_numeric(self):
        assert evaluate_criterion(crit(compare_value=None), Response("c1", "5")).verdict \
            is Verdict.NOT_STATED


class TestScreenBid:
    def test_only_pq_criteria_are_screened(self):
        cs = [crit(), Criterion("t1", "technical", "arch", 20)]
        assert len(screen_bid(cs, [Response("c1", "12")])) == 1

    def test_auto_non_responsive_only_on_definite_failure(self):
        assert auto_non_responsive(screen_bid([crit()], [Response("c1", "8")])) is True
        assert auto_non_responsive(screen_bid([crit()], [Response("c1", "x")])) is False
        assert auto_non_responsive(screen_bid([crit()], [])) is False


def test_unsupported_operator_raises_rather_than_guessing():
    """A comparison operator the gate does not understand must blow up, not silently pass or
    silently fail — either would decide a bidder's eligibility by accident."""
    import pytest

    from evaluate.deterministic.screening import _cmp

    with pytest.raises(ValueError, match="unsupported comparison operator"):
        _cmp("~=", 1, 2)


class TestPresentOperator:
    """`present` asks whether a value exists at all. It reached _cmp and raised ValueError,
    which would 500 the screening request for any RFP saying 'shall furnish'."""

    def test_present_with_a_value_meets(self):
        c = crit(compare_op="present", compare_value=None)
        assert evaluate_criterion(c, Response("c1", "BG no. 0091/2026")).verdict is Verdict.MEETS

    def test_present_without_a_value_is_not_stated(self):
        c = crit(compare_op="present", compare_value=None)
        assert evaluate_criterion(c, Response("c1", "")).verdict is Verdict.NOT_STATED

    def test_present_on_a_date_criterion_does_not_raise(self):
        c = crit(compare_kind=CompareKind.DATE, compare_op="present", compare_value=None)
        assert evaluate_criterion(c, Response("c1", "2027-01-01")).verdict is Verdict.MEETS


def test_present_is_coerced_away_from_date_criteria_by_the_extractor():
    """Guards the coercion in pipeline/extractor.py from the screening side: a date criterion
    carrying `present` accepts an EXPIRED certificate, which is why the extractor rewrites it
    to `>=`. If someone ever removes that coercion, this is what it costs."""
    expired = crit(compare_kind=CompareKind.DATE, compare_op="present", compare_value="2026-07-20")
    assert evaluate_criterion(expired, Response("c1", "2026-02-14")).verdict is Verdict.MEETS

    corrected = crit(compare_kind=CompareKind.DATE, compare_op=">=", compare_value="2026-07-20")
    assert evaluate_criterion(corrected, Response("c1", "2026-02-14")).verdict is Verdict.FAILS
