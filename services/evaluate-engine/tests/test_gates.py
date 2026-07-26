from decimal import Decimal

from evaluate.deterministic.gates import (
    Blocker,
    committee_mark,
    qualified,
    requires_consensus,
    technical_lock_blockers,
    technical_score,
)
from evaluate.deterministic.types import CriterionAggregate


def agg(marks, max_marks=20, consensus=None):
    return CriterionAggregate("c1", max_marks, tuple(Decimal(str(m)) for m in marks),
                              Decimal(str(consensus)) if consensus is not None else None)


class TestConsensus:
    def test_close_marks_use_the_mean(self):
        a = agg([14, 15, 16])          # spread 2, threshold 4
        assert requires_consensus(a) is False
        assert committee_mark(a) == Decimal(15)

    def test_wide_spread_has_no_committee_mark_until_consensus(self):
        a = agg([12, 15, 18])          # spread 6 >= 4
        assert requires_consensus(a) is True
        assert committee_mark(a) is None, "the mean must NOT quietly stand on a disputed criterion"

    def test_recorded_consensus_settles_it(self):
        assert committee_mark(agg([12, 15, 18], consensus=15)) == Decimal(15)

    def test_consensus_wins_even_when_no_dispute(self):
        assert committee_mark(agg([14, 15, 16], consensus=13)) == Decimal(13)

    def test_single_evaluator_never_requires_consensus(self):
        assert requires_consensus(agg([12])) is False
        assert committee_mark(agg([12])) == Decimal(12)

    def test_no_marks_means_no_mark(self):
        assert committee_mark(agg([])) is None

    def test_zero_max_marks_cannot_require_consensus(self):
        assert requires_consensus(agg([1, 9], max_marks=0)) is False

    def test_spread_exactly_at_threshold_requires_consensus(self):
        assert requires_consensus(agg([12, 16])) is True   # spread 4 == 0.20*20


class TestTechnicalScore:
    def test_sums_settled_criteria(self):
        assert technical_score([agg([10]), agg([8])]) == Decimal(18)

    def test_unsettled_criterion_blocks_the_total(self):
        assert technical_score([agg([10]), agg([12, 18])]) is None


class TestQualification:
    def test_threshold_is_inclusive(self):
        assert qualified(Decimal(65), 65) is True
        assert qualified(Decimal("64.99"), 65) is False


class TestLockBlockers:
    def test_below_quorum_blocks(self):
        b = technical_lock_blockers(submitted_evaluators=2, quorum=3, unsettled=[])
        assert [x.code for x in b] == ["QUORUM_NOT_MET"]

    def test_unsettled_criteria_block(self):
        b = technical_lock_blockers(submitted_evaluators=3, quorum=3, unsettled=["c1", "c2"])
        assert [x.code for x in b] == ["CONSENSUS_REQUIRED"]
        assert "2" in b[0].detail

    def test_both_can_block_at_once(self):
        b = technical_lock_blockers(submitted_evaluators=1, quorum=3, unsettled=["c1"])
        assert {x.code for x in b} == {"QUORUM_NOT_MET", "CONSENSUS_REQUIRED"}

    def test_clean_state_has_no_blockers(self):
        assert technical_lock_blockers(submitted_evaluators=3, quorum=3, unsettled=()) == ()

    def test_removing_a_member_does_not_lower_quorum(self):
        # The rule a losing bidder's lawyer checks first: you cannot reach quorum by shrinking
        # the committee. Quorum is passed in from the evaluation, never derived from members.
        assert technical_lock_blockers(submitted_evaluators=2, quorum=3, unsettled=[])[0].code \
            == "QUORUM_NOT_MET"


def test_blocker_is_hashable_and_comparable():
    assert Blocker("A", "b") == Blocker("A", "b")
