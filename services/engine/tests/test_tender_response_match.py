"""evals/tender_response/match.py — the requirement matcher and its corrupted controls.

Synthetic in-memory requirement rows (not customer data) — the matcher only needs
requirement_id/page_number/page_end/requirement_text.
"""

from __future__ import annotations

from evals.tender_response.match import (
    TOKEN_MATCH_THRESHOLD,
    match_requirements,
    normalize_tokens,
    page_range,
    ranges_overlap,
    token_coverage,
)


def _req(rid: str, page: int, text: str, page_end: int | None = None) -> dict:
    return {"requirement_id": rid, "page_number": page, "page_end": page_end,
            "requirement_text": text}


def test_identical_golden_and_pred_match_everything():
    golds = [_req("G1", 1, "Bidder must submit a valid EMD of Rs 50000."),
             _req("G2", 3, "Three years of relevant manufacturing experience required.")]
    preds = [_req("P1", 1, "Bidder must submit a valid EMD of Rs 50000."),
             _req("P2", 3, "Three years of relevant manufacturing experience required.")]
    m = match_requirements(golds, preds)
    assert m.matched == {"G1": "P1", "G2": "P2"}
    assert m.unmatched_gold == []
    assert m.unmatched_pred == []


def test_paraphrase_with_zero_word_overlap_is_a_miss():
    # control (b): same page, totally different vocabulary — must NOT be credited as a match.
    golds = [_req("G1", 5, "Earnest money deposit of fifty thousand rupees is mandatory.")]
    preds = [_req("P1", 5, "Kindly refer annexure seven for pricing schedule details.")]
    m = match_requirements(golds, preds)
    assert m.matched == {}
    assert m.unmatched_gold == ["G1"]
    assert m.unmatched_pred == ["P1"]


def test_page_shift_beyond_range_breaks_an_otherwise_perfect_match():
    # control (c): identical text, but the predicted anchor no longer overlaps the gold page.
    text = "Bidder must hold a valid factory licence at the time of bidding."
    golds = [_req("G1", 4, text, page_end=4)]
    preds = [_req("P1", 5, text, page_end=5)]  # shifted +1, no overlap with [4,4]
    m = match_requirements(golds, preds)
    assert m.matched == {}
    assert m.unmatched_gold == ["G1"]


def test_page_ranges_that_overlap_at_the_boundary_still_match():
    text = "Integrity pact must be signed and uploaded with the bid."
    golds = [_req("G1", 2, text, page_end=4)]
    preds = [_req("P1", 4, text, page_end=6)]  # overlaps at page 4
    m = match_requirements(golds, preds)
    assert m.matched == {"G1": "P1"}


def test_greedy_assignment_is_one_to_one_not_many_to_one():
    text = "Bank guarantee of ten percent contract value required for performance security."
    golds = [_req("G1", 1, text)]
    preds = [
        _req("P1", 1, text),  # perfect, identical text
        _req("P2", 1, text + " Additional unrelated padding words here too."),  # also qualifies
    ]
    m = match_requirements(golds, preds)
    assert len(m.matched) == 1
    assert set(m.matched.values()) <= {"P1", "P2"}
    assert len(m.unmatched_pred) == 1  # the loser is reported, not silently dropped


def test_token_coverage_threshold_is_the_architecture_spec_value():
    assert TOKEN_MATCH_THRESHOLD == 0.8


def test_token_coverage_is_asymmetric_on_gold_vocabulary():
    gold = normalize_tokens("alpha beta gamma")
    pred_missing_one = normalize_tokens("alpha beta")
    pred_superset = normalize_tokens("alpha beta gamma delta epsilon")
    assert token_coverage(gold, pred_missing_one) == 2 / 3
    assert token_coverage(gold, pred_superset) == 1.0


def test_page_range_defaults_page_end_to_page_number():
    assert page_range({"page_number": 7, "page_end": None}) == (7, 7)
    assert page_range({"page_number": 7, "page_end": 9}) == (7, 9)


def test_ranges_overlap_boundary_cases():
    assert ranges_overlap((1, 3), (3, 5))
    assert not ranges_overlap((1, 3), (4, 5))
