from decimal import Decimal

import pytest

from evaluate.deterministic.qcbs import financial_score, has_unresolved_tie, rank


def bid(bid_id, name, tech, q=True, amount=None):
    return {"bid_id": bid_id, "bidder_name": name, "technical_score": tech,
            "technically_qualified": q, "amount": amount}


class TestFinancialScore:
    def test_lowest_scores_100(self):
        assert financial_score(Decimal(100), Decimal(100)) == Decimal(100)

    def test_double_the_price_scores_half(self):
        assert financial_score(Decimal(200), Decimal(100)) == Decimal(50)

    def test_zero_or_negative_is_rejected(self):
        with pytest.raises(ValueError):
            financial_score(Decimal(0), Decimal(100))


class TestRank:
    def test_combines_with_published_weights(self):
        r = rank([bid("b1", "A", 80, amount=100)], technical_weight=70,
                 financial_weight=30, max_technical_marks=100)
        # tech 80% * 70 + fin 100 * 30, /100 = 56 + 30 = 86
        assert r[0].combined_score == Decimal("86.00")
        assert r[0].rank == 1

    def test_unqualified_bid_is_never_ranked(self):
        r = rank([bid("b1", "A", 80, amount=100), bid("b2", "B", 50, q=False, amount=50)],
                 technical_weight=70, financial_weight=30, max_technical_marks=100)
        assert [x.rank for x in r if x.bid_id == "b2"] == [None]

    def test_qualified_bid_without_a_price_is_not_ranked(self):
        r = rank([bid("b1", "A", 80, amount=None)], technical_weight=70,
                 financial_weight=30, max_technical_marks=100)
        assert r[0].rank is None and r[0].combined_score is None

    def test_exact_tie_is_reported_not_broken(self):
        r = rank([bid("b1", "A", 80, amount=100), bid("b2", "B", 80, amount=100)],
                 technical_weight=70, financial_weight=30, max_technical_marks=100)
        assert {x.rank for x in r} == {1}
        assert all(x.tied_with for x in r), "software must not silently order a tie"
        assert has_unresolved_tie(r) is True

    def test_no_tie_reports_none(self):
        r = rank([bid("b1", "A", 90, amount=100), bid("b2", "B", 70, amount=100)],
                 technical_weight=70, financial_weight=30, max_technical_marks=100)
        assert has_unresolved_tie(r) is False
        assert [x.rank for x in r] == [1, 2]

    def test_rank_positions_skip_after_a_tie(self):
        r = rank([bid("b1", "A", 80, amount=100), bid("b2", "B", 80, amount=100),
                  bid("b3", "C", 50, amount=100)],
                 technical_weight=70, financial_weight=30, max_technical_marks=100)
        assert sorted(x.rank for x in r) == [1, 1, 3]

    def test_zero_max_marks_does_not_divide_by_zero(self):
        r = rank([bid("b1", "A", 0, amount=100)], technical_weight=70,
                 financial_weight=30, max_technical_marks=0)
        assert r[0].combined_score == Decimal("30.00")

    def test_empty_input(self):
        assert rank([], technical_weight=70, financial_weight=30, max_technical_marks=100) == []
